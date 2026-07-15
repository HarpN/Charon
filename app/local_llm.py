from __future__ import annotations

import json
import os
import re

from pydantic import BaseModel, Field, ValidationError

from .config import settings

try:
    from llama_cpp import Llama
except Exception:
    Llama = None


class IntentAnalysis(BaseModel):
    status: str = Field(pattern="^(ACTIVE|PENDING_SYNC|PENDING_REVIEW|COMPLETED)$")
    completion: int = Field(ge=0, le=100)
    intent_summary: str = Field(min_length=1, max_length=400)
    nlp_engine: str = Field(min_length=1, max_length=128)
    fallback_used: bool


class LocalIntentAnalyzer:
    def __init__(self) -> None:
        self._llama = None

    def analyze(self, user_intent: str, retrieval_snippets: list[str]) -> IntentAnalysis:
        if not self._can_use_llama():
            return self._heuristic_fallback(user_intent)

        try:
            output = self._run_llama(user_intent=user_intent, retrieval_snippets=retrieval_snippets)
            parsed = self._extract_json_object(output)
            if parsed is None:
                return self._heuristic_fallback(user_intent)

            candidate = {
                "status": parsed.get("status"),
                "completion": parsed.get("completion"),
                "intent_summary": parsed.get("intent_summary", user_intent[:400] or "Intent received"),
                "nlp_engine": "llama-cpp-local",
                "fallback_used": False,
            }
            return IntentAnalysis.model_validate(candidate)
        except (ValidationError, ValueError, TypeError):
            return self._heuristic_fallback(user_intent)
        except Exception:
            return self._heuristic_fallback(user_intent)

    def _heuristic_fallback(self, user_intent: str) -> IntentAnalysis:
        normalized = user_intent.lower()
        if "complete" in normalized or "completed" in normalized:
            status, completion = "COMPLETED", 100
        elif "pause" in normalized or "hold" in normalized:
            status, completion = "PENDING_REVIEW", 0
        elif "progress" in normalized or "sync" in normalized:
            status, completion = "PENDING_SYNC", 75
        else:
            status, completion = "ACTIVE", 50

        return IntentAnalysis(
            status=status,
            completion=completion,
            intent_summary=user_intent[:400] or "Intent received",
            nlp_engine="heuristic-fallback",
            fallback_used=True,
        )

    def _can_use_llama(self) -> bool:
        if not settings.local_llm_enabled:
            return False
        if Llama is None:
            return False
        model_path = settings.local_llm_model_path.strip()
        if not model_path:
            return False
        return os.path.exists(model_path)

    def _get_llama(self):
        if self._llama is None:
            self._llama = Llama(
                model_path=settings.local_llm_model_path,
                n_ctx=settings.local_llm_context_window,
                verbose=False,
            )
        return self._llama

    def _run_llama(self, user_intent: str, retrieval_snippets: list[str]) -> str:
        snippet_block = "\n".join(f"- {snippet}" for snippet in retrieval_snippets) or "- (none)"
        prompt = (
            "You analyze user intent for a backlog update.\n"
            "Return STRICT JSON only. No markdown, no extra text.\n"
            "Required schema:\n"
            '{"status":"ACTIVE|PENDING_SYNC|PENDING_REVIEW|COMPLETED","completion":0-100,"intent_summary":"max 400 chars"}\n'
            f"User intent: {user_intent}\n"
            f"Retrieval snippets:\n{snippet_block}\n"
        )

        llm = self._get_llama()
        response = llm.create_completion(
            prompt=prompt,
            max_tokens=settings.local_llm_max_tokens,
            temperature=settings.local_llm_temperature,
        )
        return str(response["choices"][0]["text"])

    def _extract_json_object(self, text: str) -> dict | None:
        stripped = text.strip()
        if not stripped:
            return None

        decoder = json.JSONDecoder()
        candidates = [stripped]
        candidates.extend(re.findall(r"\{[\s\S]*\}", stripped))

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        for idx, ch in enumerate(stripped):
            if ch != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(stripped[idx:])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue

        return None
