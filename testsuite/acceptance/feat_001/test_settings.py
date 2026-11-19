"""feat-001 (NFR-009): settings default to mock mode and require explicit live opt-in."""

import pytest
from pydantic import ValidationError

from agentops_api.settings import Settings


def test_defaults_are_mock_and_keyless() -> None:
    settings = Settings()

    assert settings.llm_mode == "mock"
    assert settings.enable_live_llm is False
    assert settings.llm_provider == "mock"
    assert settings.llm_model == "mock-deterministic-v1"
    assert settings.database_url is None


def test_provider_keys_in_environment_do_not_enable_live_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "CANARY-SECRET-0001")
    monkeypatch.setenv("GROQ_API_KEY", "CANARY-SECRET-0002")

    settings = Settings()

    assert settings.llm_mode == "mock"
    assert settings.enable_live_llm is False


@pytest.mark.parametrize("mode", ["hosted_free", "live_paid"])
def test_live_modes_require_enable_live_llm(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    monkeypatch.setenv("LLM_MODE", mode)

    with pytest.raises(ValidationError, match="ENABLE_LIVE_LLM"):
        Settings()


def test_live_mode_with_explicit_opt_in_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "hosted_free")
    monkeypatch.setenv("ENABLE_LIVE_LLM", "true")

    assert Settings().llm_mode == "hosted_free"


def test_replay_mode_needs_no_live_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "replay")

    assert Settings().llm_mode == "replay"


def test_database_url_is_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://agentops:CANARY-SECRET-0003@localhost/agentops"
    )

    settings = Settings()

    assert "CANARY-SECRET-0003" not in repr(settings)
    assert "CANARY-SECRET-0003" not in settings.model_dump_json()


def test_env_example_declares_every_setting() -> None:
    from pathlib import Path

    declared = {
        line.split("=", 1)[0].strip()
        for line in Path(".env.example").read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }

    assert {name.upper() for name in Settings.model_fields} <= declared
    assert declared.isdisjoint({"GOOGLE_API_KEY", "GROQ_API_KEY", "LANGFUSE_SECRET_KEY"})
