from __future__ import annotations

from datetime import datetime, timezone
import os

import grpc
import pytest
from google.protobuf import empty_pb2, json_format, struct_pb2

os.environ["INBOUND_SIGNATURE_HEADER"] = "X-Judy-Signature"
os.environ["INBOUND_SIGNATURE_SECRET"] = "charon-inbound-secret"

from app.grpc_server import create_server, client, metrics
from app.signer import sign_payload


@pytest.fixture(scope="module")
def channel() -> grpc.Channel:
    for key in metrics:
        metrics[key] = 0

    server = create_server(bind_address="127.0.0.1:0")
    server.start()

    grpc_channel = grpc.insecure_channel(f"127.0.0.1:{server.bound_port}")
    grpc.channel_ready_future(grpc_channel).result(timeout=5)

    yield grpc_channel

    grpc_channel.close()
    server.stop(None)


def _health_call(channel: grpc.Channel):
    return channel.unary_unary(
        "/charon.CharonService/Health",
        request_serializer=empty_pb2.Empty.SerializeToString,
        response_deserializer=struct_pb2.Struct.FromString,
    )


def _propose_call(channel: grpc.Channel):
    return channel.unary_unary(
        "/charon.CharonService/ProposeTask",
        request_serializer=struct_pb2.Struct.SerializeToString,
        response_deserializer=struct_pb2.Struct.FromString,
    )


def _signed_metadata(payload: dict, *, nonce: str = "nonce-charon-test", issued_at: str | None = None) -> tuple[tuple[str, str], ...]:
    message = struct_pb2.Struct()
    json_format.ParseDict(payload, message)
    normalized = json_format.MessageToDict(message)
    signature = sign_payload("charon-inbound-secret", normalized)
    metadata_issued_at = issued_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return (
        ("x-judy-signature", signature),
        ("x-charon-issued-at", metadata_issued_at),
        ("x-charon-nonce", nonce),
    )


def test_health(channel: grpc.Channel) -> None:
    response = _health_call(channel)(empty_pb2.Empty())
    payload = json_format.MessageToDict(response)
    assert payload["status"] == "ok"
    assert payload["transport"] == "grpc"


def test_propose_judge_mode(channel: grpc.Channel, monkeypatch) -> None:
    def fake_send_proposal(proposal, commit):
        assert commit is False
        return {"final_verdict": "APPROVED", "council_id": "council-alpha"}

    monkeypatch.setattr(client, "send_proposal", fake_send_proposal)

    request = struct_pb2.Struct()
    json_format.ParseDict(
        {
            "user_intent": "User confirmed this game is completed",
            "entity_id": "game_204",
            "commit": False,
        },
        request,
    )

    response = _propose_call(channel)(
        request,
        metadata=_signed_metadata(
            {
                "user_intent": "User confirmed this game is completed",
                "entity_id": "game_204",
                "commit": False,
            },
            nonce="nonce-charon-judge-1",
        ),
    )
    payload = json_format.MessageToDict(response)
    assert payload["mode"] == "judge"
    assert payload["judy_response"]["final_verdict"] == "APPROVED"


def test_propose_commit_mode(channel: grpc.Channel, monkeypatch) -> None:
    def fake_send_proposal(proposal, commit):
        assert commit is True
        return {"committed": True, "decision": {"final_verdict": "APPROVED"}}

    monkeypatch.setattr(client, "send_proposal", fake_send_proposal)

    request = struct_pb2.Struct()
    json_format.ParseDict(
        {
            "user_intent": "Sync this progress to storage",
            "entity_id": "game_300",
            "commit": True,
        },
        request,
    )

    response = _propose_call(channel)(
        request,
        metadata=_signed_metadata(
            {
                "user_intent": "Sync this progress to storage",
                "entity_id": "game_300",
                "commit": True,
            },
            nonce="nonce-charon-commit-1",
        ),
    )
    payload = json_format.MessageToDict(response)
    assert payload["mode"] == "commit"
    assert payload["judy_response"]["committed"] is True


def test_propose_rejects_invalid_signature(channel: grpc.Channel) -> None:
    request = struct_pb2.Struct()
    payload = {
        "user_intent": "Sync this progress to storage",
        "entity_id": "game_300",
        "commit": True,
    }
    json_format.ParseDict(payload, request)

    with pytest.raises(grpc.RpcError) as exc:
        _propose_call(channel)(
            request,
            metadata=(
                ("x-judy-signature", "bad-signature"),
                ("x-charon-issued-at", datetime.now(timezone.utc).replace(microsecond=0).isoformat()),
                ("x-charon-nonce", "nonce-charon-bad-1"),
            ),
        )

    assert exc.value.code() == grpc.StatusCode.UNAUTHENTICATED
