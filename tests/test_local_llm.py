from __future__ import annotations

from app.config import settings
from app.local_llm import LocalIntentAnalyzer


def test_fallback_completed_intent(monkeypatch) -> None:
    monkeypatch.setattr(settings, "local_llm_enabled", False)
    analyzer = LocalIntentAnalyzer()

    result = analyzer.analyze("Mark this game as completed", [])

    assert result.status == "COMPLETED"
    assert result.completion == 100
    assert result.fallback_used is True


def test_fallback_pause_intent(monkeypatch) -> None:
    monkeypatch.setattr(settings, "local_llm_enabled", False)
    analyzer = LocalIntentAnalyzer()

    result = analyzer.analyze("Pause this backlog item for now", [])

    assert result.status == "PENDING_REVIEW"
    assert result.completion == 0
    assert result.fallback_used is True


def test_fallback_sync_intent(monkeypatch) -> None:
    monkeypatch.setattr(settings, "local_llm_enabled", False)
    analyzer = LocalIntentAnalyzer()

    result = analyzer.analyze("Sync progress to tracker", [])

    assert result.status == "PENDING_SYNC"
    assert result.completion == 75
    assert result.fallback_used is True


def test_fallback_default_intent(monkeypatch) -> None:
    monkeypatch.setattr(settings, "local_llm_enabled", False)
    analyzer = LocalIntentAnalyzer()

    result = analyzer.analyze("Investigate next action", [])

    assert result.status == "ACTIVE"
    assert result.completion == 50
    assert result.fallback_used is True
