"""Tests for Gemini AI fallback behavior in the master pipeline."""

from pathlib import Path

import pytest

from f1_predictions.utils.config import Settings
from scripts.master_pipeline import call_ai_with_retry, setup_gemini


class _FakeResponse:
    """Minimal Gemini response object for AI caller tests."""

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModels:
    """Fake Gemini models namespace that returns or raises configured outcomes."""

    def __init__(self, outcomes: dict[str, list[object]]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    def generate_content(self, model: str, contents: str) -> _FakeResponse:
        self.calls.append(model)
        outcome = self.outcomes[model].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return _FakeResponse(str(outcome))


class _FakeClient:
    """Fake Gemini client exposing the same .models shape as google-genai."""

    def __init__(self, outcomes: dict[str, list[object]]) -> None:
        self.models = _FakeModels(outcomes)


def test_call_ai_with_retry_primary_success() -> None:
    """The primary Gemini model is used when it succeeds."""
    client = _FakeClient({"gemini-3.1-pro-preview": ["primary report"]})

    result = call_ai_with_retry(
        "prompt",
        client,  # type: ignore[arg-type]
        ["gemini-3.1-pro-preview", "gemini-3.5-flash"],
        retries=0,
        delay=0,
    )

    assert result == "primary report"
    assert client.models.calls == ["gemini-3.1-pro-preview"]


def test_call_ai_with_retry_fallback_success() -> None:
    """The fallback Gemini model is used after primary failure."""
    client = _FakeClient(
        {
            "gemini-3.1-pro-preview": [RuntimeError("quota exhausted")],
            "gemini-3.5-flash": ["fallback report"],
        }
    )

    result = call_ai_with_retry(
        "prompt",
        client,  # type: ignore[arg-type]
        ["gemini-3.1-pro-preview", "gemini-3.5-flash"],
        retries=0,
        delay=0,
    )

    assert result == "fallback report"
    assert client.models.calls == ["gemini-3.1-pro-preview", "gemini-3.5-flash"]


def test_call_ai_with_retry_returns_none_when_all_models_fail() -> None:
    """The caller returns None so the pipeline can use local fallback copy."""
    client = _FakeClient(
        {
            "gemini-3.1-pro-preview": [RuntimeError("quota exhausted")],
            "gemini-3.5-flash": [RuntimeError("service unavailable")],
        }
    )

    result = call_ai_with_retry(
        "prompt",
        client,  # type: ignore[arg-type]
        ["gemini-3.1-pro-preview", "gemini-3.5-flash"],
        retries=0,
        delay=0,
    )

    assert result is None
    assert client.models.calls == ["gemini-3.1-pro-preview", "gemini-3.5-flash"]


def test_setup_gemini_skips_missing_api_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing Gemini API key disables AI without crashing the pipeline."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("F1_GEMINI_API_KEY", raising=False)

    settings = Settings()

    assert setup_gemini(settings) is None
