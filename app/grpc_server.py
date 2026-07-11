from __future__ import annotations

from concurrent import futures
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

import grpc
from google.protobuf import empty_pb2, json_format, struct_pb2

from .config import settings
from .judy_client import JudyClient
from .models import CharonTaskRequest
from .orchestrator import build_proposal
from .signer import verify_signature

client = JudyClient()

# Lightweight in-memory counters for quick local observability.
metrics: dict[str, int] = {
    "requests_total": 0,
    "proposals_sent_total": 0,
    "proposal_errors_total": 0,
}
_metrics_lock = Lock()
_replay_lock = Lock()
_seen_nonces: dict[str, datetime] = {}

_SERVICE_NAME = "charon.CharonService"


def _dict_to_struct(payload: dict[str, Any]) -> struct_pb2.Struct:
    message = struct_pb2.Struct()
    json_format.ParseDict(payload, message)
    return message


def _struct_to_dict(message: struct_pb2.Struct) -> dict[str, Any]:
    return json_format.MessageToDict(message)


def _health(_: empty_pb2.Empty, context: grpc.ServicerContext) -> struct_pb2.Struct:
    del context
    return _dict_to_struct(
        {
            "status": "ok",
            "service": settings.service_name,
            "transport": "grpc",
            "judy_grpc_target": settings.judy_grpc_target,
        }
    )


def _get_metrics(_: empty_pb2.Empty, context: grpc.ServicerContext) -> struct_pb2.Struct:
    del context
    with _metrics_lock:
        return _dict_to_struct(dict(metrics))


def _metadata_dict(context: grpc.ServicerContext) -> dict[str, str]:
    return {item.key.lower(): item.value for item in context.invocation_metadata()}


def _verify_inbound_signature(context: grpc.ServicerContext, payload: dict[str, Any]) -> bool:
    metadata = _metadata_dict(context)
    signature = metadata.get(settings.inbound_signature_header.lower())
    if not signature:
        context.set_code(grpc.StatusCode.UNAUTHENTICATED)
        context.set_details("Missing signature metadata")
        return False

    if not verify_signature(settings.inbound_signature_secret, payload, signature):
        context.set_code(grpc.StatusCode.UNAUTHENTICATED)
        context.set_details("Invalid signature")
        return False

    return True


def _validate_replay_window(context: grpc.ServicerContext) -> bool:
    metadata = _metadata_dict(context)
    issued_at = metadata.get("x-charon-issued-at")
    nonce = metadata.get("x-charon-nonce")
    if not issued_at or not nonce:
        context.set_code(grpc.StatusCode.UNAUTHENTICATED)
        context.set_details("Missing replay metadata")
        return False

    try:
        issued = datetime.fromisoformat(issued_at.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
        context.set_details("Invalid x-charon-issued-at timestamp")
        return False

    now = datetime.now(timezone.utc)
    ttl = timedelta(seconds=settings.replay_ttl_seconds)
    if issued < now - ttl or issued > now + ttl:
        context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
        context.set_details("Replay window validation failed")
        return False

    with _replay_lock:
        expired_before = now - ttl
        for seen_nonce in [key for key, seen_time in _seen_nonces.items() if seen_time < expired_before]:
            _seen_nonces.pop(seen_nonce, None)

        if nonce in _seen_nonces:
            context.set_code(grpc.StatusCode.ALREADY_EXISTS)
            context.set_details("Nonce replay detected")
            return False

        _seen_nonces[nonce] = now

    return True


def _propose_task(request: struct_pb2.Struct, context: grpc.ServicerContext) -> struct_pb2.Struct:
    with _metrics_lock:
        metrics["requests_total"] += 1

    payload = _struct_to_dict(request)
    if not _verify_inbound_signature(context, payload):
        with _metrics_lock:
            metrics["proposal_errors_total"] += 1
        return struct_pb2.Struct()
    if not _validate_replay_window(context):
        with _metrics_lock:
            metrics["proposal_errors_total"] += 1
        return struct_pb2.Struct()

    try:
        request_model = CharonTaskRequest.model_validate(payload)
    except Exception as exc:
        context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
        context.set_details(f"Invalid request: {exc}")
        with _metrics_lock:
            metrics["proposal_errors_total"] += 1
        return struct_pb2.Struct()

    proposal = build_proposal(request_model)

    try:
        judy_response = client.send_proposal(proposal, commit=request_model.commit)
        with _metrics_lock:
            metrics["proposals_sent_total"] += 1
    except Exception as exc:
        with _metrics_lock:
            metrics["proposal_errors_total"] += 1
        context.set_code(grpc.StatusCode.UNAVAILABLE)
        context.set_details(f"Unable to reach Judy Council: {exc}")
        return struct_pb2.Struct()

    return _dict_to_struct(
        {
            "correlation_id": proposal.transaction_metadata.correlation_id,
            "mode": "commit" if request_model.commit else "judge",
            "proposal": proposal.model_dump(),
            "judy_response": judy_response,
        }
    )


def create_server(bind_address: str | None = None) -> grpc.Server:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=settings.grpc_max_workers))

    handlers = {
        "Health": grpc.unary_unary_rpc_method_handler(
            _health,
            request_deserializer=empty_pb2.Empty.FromString,
            response_serializer=struct_pb2.Struct.SerializeToString,
        ),
        "GetMetrics": grpc.unary_unary_rpc_method_handler(
            _get_metrics,
            request_deserializer=empty_pb2.Empty.FromString,
            response_serializer=struct_pb2.Struct.SerializeToString,
        ),
        "ProposeTask": grpc.unary_unary_rpc_method_handler(
            _propose_task,
            request_deserializer=struct_pb2.Struct.FromString,
            response_serializer=struct_pb2.Struct.SerializeToString,
        ),
    }

    server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(_SERVICE_NAME, handlers),))

    listen_address = bind_address or f"{settings.host}:{settings.grpc_port}"
    if settings.grpc_tls_enabled:
        with open(settings.grpc_tls_server_key_path, "rb") as key_file:
            private_key = key_file.read()
        with open(settings.grpc_tls_server_cert_path, "rb") as cert_file:
            certificate_chain = cert_file.read()

        root_certificates = None
        if settings.grpc_tls_client_ca_cert_path:
            with open(settings.grpc_tls_client_ca_cert_path, "rb") as ca_file:
                root_certificates = ca_file.read()

        credentials = grpc.ssl_server_credentials(
            [(private_key, certificate_chain)],
            root_certificates=root_certificates,
            require_client_auth=settings.grpc_tls_require_client_auth,
        )
        bound_port = server.add_secure_port(listen_address, credentials)
    else:
        bound_port = server.add_insecure_port(listen_address)

    if not bound_port:
        raise RuntimeError("Failed to bind Charon gRPC server")

    server.bound_port = bound_port  # type: ignore[attr-defined]
    return server


def serve() -> None:
    server = create_server()
    server.start()
    server.wait_for_termination()
