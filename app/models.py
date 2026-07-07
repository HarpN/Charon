from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CharonTaskRequest(BaseModel):
    user_intent: str = Field(..., min_length=1, max_length=600)
    entity_id: str = Field(default="game_105", min_length=1)
    target_table: str = Field(default="local_backlog", min_length=1)
    action_type: str = Field(default="UPDATE_STATUS", min_length=1)
    commit: bool = Field(default=False)


class TransactionMetadata(BaseModel):
    agent_id: str
    timestamp: str
    correlation_id: str


class ProposedAction(BaseModel):
    target_table: str
    action_type: str
    entity_id: str
    payload: dict[str, Any]


class ProposalPayload(BaseModel):
    transaction_metadata: TransactionMetadata
    proposed_action: ProposedAction
    agent_rationale: str


class CharonTaskResponse(BaseModel):
    correlation_id: str
    mode: str
    proposal: dict[str, Any]
    judy_response: dict[str, Any]


class HealthResponse(BaseModel):
    status: str
    service: str
    judy_base_url: str
