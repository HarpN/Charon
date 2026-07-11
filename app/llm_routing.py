from __future__ import annotations

from pydantic import BaseModel, Field

from .config import settings


class RoutingDecision(BaseModel):
    model_tier: str = Field(pattern="^(light|deep)$")
    selected_model: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=256)


_DEEP_HINTS = (
    "comprehensive",
    "deep",
    "full plan",
    "full strategy",
    "breakdown",
    "roadmap",
    "optimize",
    "best route",
    "long term",
)


def route_intent(user_intent: str) -> RoutingDecision:
    normalized = user_intent.lower()
    is_deep = any(hint in normalized for hint in _DEEP_HINTS)
    if is_deep:
        return RoutingDecision(
            model_tier="deep",
            selected_model=settings.llm_deep_model,
            reason="Intent requests intensive planning or strategy depth",
        )

    return RoutingDecision(
        model_tier="light",
        selected_model=settings.llm_light_model,
        reason="Intent can be handled by low-cost routing and formatting",
    )
