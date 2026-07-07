from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .config import settings
from .judy_client import JudyClient
from .models import CharonTaskRequest, CharonTaskResponse, HealthResponse
from .orchestrator import build_proposal

app = FastAPI(title="Charon Agent", version=settings.service_version)
client = JudyClient()

# Lightweight in-memory counters for quick local observability.
metrics = {
    "requests_total": 0,
    "proposals_sent_total": 0,
    "proposal_errors_total": 0,
}


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        judy_base_url=settings.judy_base_url,
    )


@app.get("/metrics")
def read_metrics() -> dict[str, int]:
    return metrics


@app.post("/tasks/propose", response_model=CharonTaskResponse)
def propose_task(request: CharonTaskRequest) -> CharonTaskResponse:
    metrics["requests_total"] += 1
    proposal = build_proposal(request)

    try:
        judy_response = client.send_proposal(proposal, commit=request.commit)
        metrics["proposals_sent_total"] += 1
    except Exception as exc:
        metrics["proposal_errors_total"] += 1
        raise HTTPException(status_code=502, detail=f"Unable to reach Judy Council: {exc}") from exc

    return CharonTaskResponse(
        correlation_id=proposal.transaction_metadata.correlation_id,
        mode="commit" if request.commit else "judge",
        proposal=proposal.model_dump(),
        judy_response=judy_response,
    )
