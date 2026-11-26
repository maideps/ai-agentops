"""feat-024: the demo replays are current and can be re-recorded at any time.

Recording failed when a replay's checkpoint thread survived from an earlier recording: the new
run continued the old thread's state, whose approval the reseed had deleted. Run ids are now
single-use in run_task, and the recorder clears its own fixed replay threads first.
"""

import json
from pathlib import Path

import psycopg
import pytest

from agentops_agents.checkpoints import postgres_checkpointer
from agentops_agents.state import RunDetail, TaskRequest
from agentops_agents.workflow import RunDependencies, run_task, thread_id_for
from agentops_core.aio import run as run_async
from agentops_core.llm import LLMGateway
from agentops_evals.corpus import load_corpus
from agentops_evals.replays import Replay, _catalog, record_replays
from agentops_llm.mock import MOCK_MODEL, MockLLMProvider, MockScript
from agentops_retrieval.embedding import HashingEmbedder
from agentops_tools.gateway import ToolGateway

REPLAYS = Path("fixtures/replays")
CASE_REPLAYS = {"viewer-denied": "access-01", "missing-data": "missing-01"}


def _fixture(replay_id: str) -> RunDetail:
    raw = json.loads((REPLAYS / f"replay-{replay_id}.json").read_text(encoding="utf-8"))
    assert "evidence_gaps" in raw, f"{replay_id} predates feat-023"
    return RunDetail.model_validate(raw)


@pytest.mark.parametrize("replay", _catalog(), ids=lambda r: r.id)
def test_committed_replays_match_the_current_catalog(replay: Replay) -> None:
    detail = _fixture(replay.id)
    assert detail.task_text == replay.task_text
    assert detail.trace_id == replay.trace_id


def test_case_replays_use_the_current_corpus_tasks() -> None:
    cases = {c.id: c for c in load_corpus().cases}
    for replay_id, case_id in CASE_REPLAYS.items():
        assert _fixture(replay_id).task_text == cases[case_id].task_text


def test_the_viewer_replay_records_the_sales_gap() -> None:
    detail = _fixture("viewer-denied")
    assert [(g.tool, g.source) for g in detail.evidence_gaps] == [
        ("get_sales_summary", "sales data")
    ]
    assert detail.status.value == "abstained"
    assert all(not _fixture(r).evidence_gaps for r in ("missing-data", "approved-ticket"))


@pytest.mark.integration
def test_replays_can_be_recorded_twice_in_a_row(
    seeded_db: str, analytics_dsn: str, app_dsn: str, tmp_path: Path
) -> None:
    for out in (tmp_path / "first", tmp_path / "second"):
        out.mkdir()
        ids = record_replays(analytics_dsn=analytics_dsn, app_dsn=app_dsn, out_dir=out)
        assert ids == ["sample-q3-declines", *(r.id for r in _catalog())]
    index = json.loads((tmp_path / "second" / "index.json").read_text(encoding="utf-8"))
    assert [e["id"] for e in index["replays"]] == ids
    ticket = json.loads(
        (tmp_path / "second" / "replay-approved-ticket.json").read_text(encoding="utf-8")
    )
    assert ticket["status"] == "completed"
    assert ticket["action_result"]["status"] == "created"
    viewer = json.loads(
        (tmp_path / "second" / "replay-viewer-denied.json").read_text(encoding="utf-8")
    )
    assert [g["tool"] for g in viewer["evidence_gaps"]] == ["get_sales_summary"]


@pytest.mark.integration
def test_a_run_id_with_checkpoints_cannot_start_a_new_run(
    seeded_db: str, analytics_dsn: str, app_dsn: str
) -> None:
    run_id = "feat024-single-use"
    turns = [{"text": json.dumps({"summary": "Nothing.", "findings": []})}]
    request = TaskRequest(
        run_id=run_id, tenant_id="demo-a", user_id="user-a-analyst", task_text="Summarize."
    )
    embedder = HashingEmbedder()

    async def start(*, clear: bool) -> RunDetail:
        async with postgres_checkpointer(app_dsn, tenant_id="demo-a") as saver:
            script = MockScript.model_validate({"run_id": run_id, "turns": turns})
            deps = RunDependencies(
                gateway=LLMGateway(MockLLMProvider([script]), MOCK_MODEL),
                llm_provider="mock",
                llm_model=MOCK_MODEL,
                connect=lambda: psycopg.connect(analytics_dsn),
                embedder=embedder,
                tool_gateway=ToolGateway(
                    connect=lambda: psycopg.connect(app_dsn), embedder=embedder
                ),
                checkpointer=saver,
            )
            if clear:
                await saver.adelete_thread(thread_id_for("demo-a", run_id))
            return await run_task(request, deps)

    first = run_async(start(clear=True))
    assert first.status.value in {"completed", "abstained"}
    with pytest.raises(ValueError, match="already exists"):
        run_async(start(clear=False))
