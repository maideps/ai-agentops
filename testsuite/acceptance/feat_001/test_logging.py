"""feat-001: logs are structured JSON and never print environment or secret values."""

import io
import json
import logging

import pytest

from agentops_api.app import create_app
from agentops_api.logging import JsonFormatter
from agentops_api.settings import Settings


def test_formatter_emits_one_json_object_per_record() -> None:
    record = logging.LogRecord(
        "agentops.test", logging.INFO, __file__, 1, "run.started", None, None
    )
    record.fields = {"run_id": "r-1"}

    payload = json.loads(JsonFormatter().format(record))

    assert payload["event"] == "run.started"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "agentops.test"
    assert payload["run_id"] == "r-1"
    assert "ts" in payload


def test_app_startup_log_is_json_without_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql://agentops:CANARY-SECRET-0004@localhost/agentops"
    )
    monkeypatch.setenv("GOOGLE_API_KEY", "CANARY-SECRET-0005")
    stream = io.StringIO()

    create_app(Settings(), log_stream=stream)

    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    created = [line for line in lines if line["event"] == "app.created"]
    assert len(created) == 1
    assert created[0]["llm_mode"] == "mock"
    assert "CANARY-SECRET" not in stream.getvalue()
