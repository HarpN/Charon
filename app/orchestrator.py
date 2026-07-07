from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from .config import settings
from .models import CharonTaskRequest, ProposalPayload, ProposedAction, TransactionMetadata


def _derive_update(user_intent: str) -> tuple[str, int]:
    normalized = user_intent.lower()
    if "complete" in normalized or "completed" in normalized:
        return "COMPLETED", 100
    if "pause" in normalized or "hold" in normalized:
        return "PENDING_REVIEW", 0
    if "progress" in normalized or "sync" in normalized:
        return "PENDING_SYNC", 75
    return "ACTIVE", 50


def build_proposal(request: CharonTaskRequest) -> ProposalPayload:
    status, completion = _derive_update(request.user_intent)
    correlation_id = f"tx-{uuid4().hex[:12]}"
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    return ProposalPayload(
        transaction_metadata=TransactionMetadata(
            agent_id=settings.agent_id,
            timestamp=timestamp,
            correlation_id=correlation_id,
        ),
        proposed_action=ProposedAction(
            target_table=request.target_table,
            action_type=request.action_type,
            entity_id=request.entity_id,
            payload={
                "status": status,
                "completion": completion,
                "completion_date": timestamp[:10],
            },
        ),
        agent_rationale=request.user_intent,
    )
