"""feat-009 (FR-015, FR-013): the replay catalog is sanitized, schema-valid synthetic run data
that the demo UI can show without any backend or model."""

import json
import re
from pathlib import Path
from typing import Any

import pytest

from agentops_agents.state import RunDetail, RunStatus
from agentops_telemetry.redaction import redact

REPLAYS = Path(__file__).resolve().parents[3] / "fixtures" / "replays"


def _index() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = json.loads(
        (REPLAYS / "index.json").read_text(encoding="utf-8")
    )["replays"]
    return entries


def _detail(entry: dict[str, Any]) -> RunDetail:
    return RunDetail.model_validate_json((REPLAYS / entry["file"]).read_text(encoding="utf-8"))


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def test_index_lists_every_replay_file_once() -> None:
    entries = _index()
    files = sorted(p.name for p in REPLAYS.glob("*.json") if p.name != "index.json")

    assert sorted(e["file"] for e in entries) == files
    assert len({e["id"] for e in entries}) == len(entries) >= 5
    for entry in entries:
        assert re.fullmatch(r"[a-z0-9][a-z0-9-]*", entry["id"])
        assert entry["title"] and entry["description"]


@pytest.mark.parametrize("entry", _index(), ids=lambda e: e["id"])
def test_each_replay_is_a_valid_sanitized_run_detail(entry: dict[str, Any]) -> None:
    detail = _detail(entry)
    raw = json.loads((REPLAYS / entry["file"]).read_text(encoding="utf-8"))

    assert re.fullmatch(r"[0-9a-f]{32}", detail.trace_id)
    assert detail.policy_decisions, "every run records at least one policy decision"
    for text in _strings(raw):
        assert redact(text) == text, f"replay {entry['id']} contains secret-like text: {text[:60]}"
        assert "CANARY" not in text


def test_catalog_covers_the_stories_the_demo_must_show() -> None:
    details = [_detail(e) for e in _index()]

    assert any(d.status is RunStatus.COMPLETED and d.report and d.report.findings for d in details)
    assert any(d.status is RunStatus.ABSTAINED for d in details)
    assert any(
        any(p.reason_code == "PERMISSION_DENIED" for p in d.policy_decisions) for d in details
    )
    assert any(
        any(p.reason_code == "UNSUPPORTED_CITATION" for p in d.policy_decisions) for d in details
    )
    approved = [d for d in details if d.proposed_action and d.action_result]
    assert approved, "one replay shows a proposed ticket, its approval and the write"
    result = approved[0].action_result or {}
    assert str(result["ticket_id"]).startswith("SBX-")
