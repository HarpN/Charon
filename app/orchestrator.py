from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from .config import settings
from .keeper_retrieval import KeeperRetriever
from .llm_routing import route_intent
from .local_llm import LocalIntentAnalyzer
from .models import CharonTaskRequest, ProposalPayload, ProposalRationaleEnvelope, ProposedAction, TransactionMetadata

retriever = KeeperRetriever()
intent_analyzer = LocalIntentAnalyzer()


def build_proposal(request: CharonTaskRequest) -> ProposalPayload:
    routing = route_intent(request.user_intent)
    snippets = retriever.retrieve(request.user_intent, top_k=settings.retrieval_top_k)
    intent_analysis = intent_analyzer.analyze(request.user_intent, snippets)
    rationale_envelope = ProposalRationaleEnvelope(
        model_tier=routing.model_tier,
        selected_model=routing.selected_model,
        intent_summary=intent_analysis.intent_summary,
        retrieval_snippets=snippets,
        nlp_engine=intent_analysis.nlp_engine,
        nlp_fallback_used=intent_analysis.fallback_used,
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
                "status": intent_analysis.status,
                "completion": intent_analysis.completion,
                "completion_date": timestamp[:10],
            },
        ),
        agent_rationale=json.dumps(rationale_envelope.model_dump(), separators=(",", ":"), sort_keys=True),
    )
