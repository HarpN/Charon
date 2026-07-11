from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from .config import settings
from .keeper_retrieval import KeeperRetriever
from .llm_routing import route_intent
from .models import CharonTaskRequest, ProposalPayload, ProposalRationaleEnvelope, ProposedAction, TransactionMetadata

retriever = KeeperRetriever()


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
    routing = route_intent(request.user_intent)
    snippets = retriever.retrieve(request.user_intent, top_k=settings.retrieval_top_k)
    rationale_envelope = ProposalRationaleEnvelope(
        model_tier=routing.model_tier,
        selected_model=routing.selected_model,
        intent_summary=request.user_intent[:400],
        retrieval_snippets=snippets,
    )

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
        agent_rationale=json.dumps(rationale_envelope.model_dump(), separators=(",", ":"), sort_keys=True),
    )
