from __future__ import annotations

import grpc
from google.protobuf import json_format, struct_pb2

from .config import settings
from .models import ProposalPayload
from .signer import sign_payload


class JudyClient:
    def __init__(self) -> None:
        self._target = settings.judy_grpc_target
        self._timeout = settings.judy_timeout_seconds

    def send_proposal(self, proposal: ProposalPayload, commit: bool) -> dict:
        method = "/judy.JudyCouncil/CommitProposal" if commit else "/judy.JudyCouncil/JudgeProposal"
        payload = proposal.model_dump()

        request_message = struct_pb2.Struct()
        json_format.ParseDict(payload, request_message)
        normalized_payload = json_format.MessageToDict(request_message)
        signature = sign_payload(settings.signature_secret, normalized_payload)

        if settings.judy_grpc_tls_enabled:
            with open(settings.judy_grpc_ca_path, "rb") as ca_file:
                root_certificates = ca_file.read()
            credentials = grpc.ssl_channel_credentials(root_certificates=root_certificates)
            channel = grpc.secure_channel(self._target, credentials)
        else:
            channel = grpc.insecure_channel(self._target)

        with channel:
            rpc = channel.unary_unary(
                method,
                request_serializer=struct_pb2.Struct.SerializeToString,
                response_deserializer=struct_pb2.Struct.FromString,
            )
            response = rpc(request_message, timeout=self._timeout, metadata=((settings.signature_header, signature),))
            return json_format.MessageToDict(response)
