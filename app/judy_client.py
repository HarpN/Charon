from __future__ import annotations

import grpc
from google.protobuf import json_format, struct_pb2

from .config import settings
from .models import ProposalPayload
from .signer import build_replay_metadata, sign_payload


class JudyClient:
    def __init__(self) -> None:
        self._target = settings.judy_grpc_target
        self._timeout = settings.judy_timeout_seconds

    def _create_channel(self):
        if not settings.judy_tls_enabled:
            return grpc.insecure_channel(self._target)

        root_certificates = None
        if settings.judy_tls_ca_cert_path:
            with open(settings.judy_tls_ca_cert_path, "rb") as ca_file:
                root_certificates = ca_file.read()

        private_key = None
        certificate_chain = None
        if settings.judy_mtls_enabled:
            with open(settings.judy_tls_client_key_path, "rb") as key_file:
                private_key = key_file.read()
            with open(settings.judy_tls_client_cert_path, "rb") as cert_file:
                certificate_chain = cert_file.read()

        credentials = grpc.ssl_channel_credentials(
            root_certificates=root_certificates,
            private_key=private_key,
            certificate_chain=certificate_chain,
        )
        return grpc.secure_channel(self._target, credentials)

    def send_proposal(self, proposal: ProposalPayload, commit: bool) -> dict:
        method = "/judy.JudyCouncil/CommitProposal" if commit else "/judy.JudyCouncil/JudgeProposal"
        payload = proposal.model_dump()

        issued_at, nonce = build_replay_metadata()
        signed_envelope = {
            "payload": payload,
            "issued_at": issued_at,
            "nonce": nonce,
            "key_id": settings.outbound_key_id,
        }

        request_message = struct_pb2.Struct()
        json_format.ParseDict(signed_envelope, request_message)
        normalized_payload = json_format.MessageToDict(request_message)
        signature = sign_payload(settings.outbound_signature_secret, normalized_payload)

        channel = self._create_channel()

        with channel:
            rpc = channel.unary_unary(
                method,
                request_serializer=struct_pb2.Struct.SerializeToString,
                response_deserializer=struct_pb2.Struct.FromString,
            )
            response = rpc(
                request_message,
                timeout=self._timeout,
                metadata=(
                    (settings.outbound_signature_header, signature),
                    ("x-charon-key-id", settings.outbound_key_id),
                    ("x-charon-issued-at", issued_at),
                    ("x-charon-nonce", nonce),
                ),
            )
            return json_format.MessageToDict(response)
