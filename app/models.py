from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CharonTaskRequest(BaseModel):
    user_intent: str = Field(..., min_length=1, max_length=600)
    entity_id: str = Field(default="game_105", min_length=1, max_length=128)
    target_table: str = Field(default="local_backlog", min_length=1, max_length=128)
    action_type: str = Field(default="UPDATE_STATUS", pattern="^(UPDATE_STATUS|SYNC_RECONCILE)$")
    commit: bool = Field(default=False)


class TransactionMetadata(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=128)
    timestamp: str = Field(..., min_length=1, max_length=64)
    correlation_id: str = Field(..., min_length=1, max_length=128)


class ProposedAction(BaseModel):
    target_table: str = Field(..., min_length=1, max_length=128)
    action_type: str = Field(..., min_length=1, max_length=128)
    entity_id: str = Field(..., min_length=1, max_length=128)
    payload: dict[str, Any]


class ProposalPayload(BaseModel):
    transaction_metadata: TransactionMetadata
    proposed_action: ProposedAction
    agent_rationale: str = Field(..., min_length=1, max_length=2000)


class ProposalRationaleEnvelope(BaseModel):
    model_tier: str = Field(pattern="^(light|deep)$")
    selected_model: str = Field(min_length=1, max_length=128)
    intent_summary: str = Field(min_length=1, max_length=400)
    retrieval_snippets: list[str] = Field(default_factory=list, max_length=3)
