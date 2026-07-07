from __future__ import annotations

from concurrent import futures
from typing import Any

import grpc
from google.protobuf import empty_pb2, json_format, struct_pb2

from .config import settings
from .judy_client import JudyClient
from .models import CharonTaskRequest
from .orchestrator import build_proposal

client = JudyClient()

# Lightweight in-memory counters for quick local observability.
metrics: dict[str, int] = {
    "requests_total": 0,
    "proposals_sent_total": 0,
    "proposal_errors_total": 0,
}

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
    return _dict_to_struct(metrics)


def _propose_task(request: struct_pb2.Struct, context: grpc.ServicerContext) -> struct_pb2.Struct:
    metrics["requests_total"] += 1

    try:
        request_model = CharonTaskRequest.model_validate(_struct_to_dict(request))
    except Exception as exc:
        context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
        context.set_details(f"Invalid request: {exc}")
        return struct_pb2.Struct()

    proposal = build_proposal(request_model)

    try:
        judy_response = client.send_proposal(proposal, commit=request_model.commit)
        metrics["proposals_sent_total"] += 1
    except Exception as exc:
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
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))

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
    server.add_insecure_port(listen_address)
    return server


def serve() -> None:
    server = create_server()
    server.start()
    server.wait_for_termination()
