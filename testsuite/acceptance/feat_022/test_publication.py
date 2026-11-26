"""feat-022: the repository is ready to be public.

No network or database: these read the repository's own files.
"""

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


def _rule(rule_id: str) -> dict[str, object]:
    rules = json.loads((REPO / ".harness" / "arch-rules.json").read_text(encoding="utf-8"))
    found = [r for r in rules.get("rules", rules) if r["id"] == rule_id]
    assert len(found) == 1
    return dict(found[0])


def test_license_is_mit_and_names_the_owner() -> None:
    text = (REPO / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License")
    assert "Copyright (c) 2026 Maidelin Prieto" in text
    assert "contributors" not in text.splitlines()[2]


def test_security_policy_routes_reports_privately() -> None:
    text = (REPO / "SECURITY.md").read_text(encoding="utf-8")
    assert "Report a vulnerability" in text
    assert "Do not open a public issue" in text


def test_env_files_stay_local_and_the_example_holds_no_values() -> None:
    ignore = (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert {".env", ".env.*", "!.env.example"} <= set(ignore)
    example = (REPO / ".env.example").read_text(encoding="utf-8").splitlines()
    secrets = [
        line
        for line in example
        if re.match(r"^[A-Z_]*(KEY|TOKEN|SECRET)=\S", line) and not line.startswith("#")
    ]
    assert secrets == []


def test_publishing_guide_lists_the_owner_steps() -> None:
    text = (REPO / "docs" / "publishing.md").read_text(encoding="utf-8")
    for step in ("Keep my email addresses private", "Private vulnerability reporting", "Public"):
        assert step in text


@pytest.mark.parametrize(
    "line",
    [
        r"see C:\Users\someone\notes.txt",
        "C:/Users/someone/notes.txt",
        "/home/alice/project",
        "/Users/alice/project",
        r"D:\7-Projects\repo",
    ],
)
def test_local_path_rule_rejects_machine_paths(line: str) -> None:
    rule = _rule("arch-107")
    assert rule["paths"] == ["**"]
    assert re.search(str(rule["pattern"]), line)


@pytest.mark.parametrize(
    "line",
    [
        "packages/agents/agentops_agents/workflow.py",
        "~/.config/tool",
        "<repo>/datasets/evals/v1",
        "https://example.com/Users/alice/",
        "ratio 3:1/2",
    ],
)
def test_local_path_rule_allows_relative_and_placeholder_paths(line: str) -> None:
    assert not re.search(str(_rule("arch-107")["pattern"]), line)
