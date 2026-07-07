from fastapi.testclient import TestClient

from app.main import app, client


test_client = TestClient(app)


def test_health() -> None:
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_propose_judge_mode(monkeypatch) -> None:
    def fake_send_proposal(proposal, commit):
        assert commit is False
        return {"final_verdict": "APPROVED", "council_id": "council-alpha"}

    monkeypatch.setattr(client, "send_proposal", fake_send_proposal)

    response = test_client.post(
        "/tasks/propose",
        json={
            "user_intent": "User confirmed this game is completed",
            "entity_id": "game_204",
            "commit": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "judge"
    assert payload["judy_response"]["final_verdict"] == "APPROVED"


def test_propose_commit_mode(monkeypatch) -> None:
    def fake_send_proposal(proposal, commit):
        assert commit is True
        return {"committed": True, "decision": {"final_verdict": "APPROVED"}}

    monkeypatch.setattr(client, "send_proposal", fake_send_proposal)

    response = test_client.post(
        "/tasks/propose",
        json={
            "user_intent": "Sync this progress to storage",
            "entity_id": "game_300",
            "commit": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "commit"
    assert payload["judy_response"]["committed"] is True
