"""feat-021 (FR-011, NFR-009): live evaluation stops when the provider quota runs out.

On 2026-11-26 the free-tier daily quota ran out after ten cases; the corpus kept retrying every
remaining case for 28 minutes and produced no usable evidence. No network: completions and
runs are stubbed, and sleeps are injected so nothing waits.
"""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from agentops_agents.state import PolicyDecision, RunDetail, RunError, RunStatus, TaskRequest
from agentops_agents.workflow import RunDependencies
from agentops_core.llm import LLMError, LLMErrorCode, Message, ModelRequest
from agentops_evals import __main__ as cli
from agentops_evals import benchmark, runner
from agentops_evals.corpus import Case, Corpus, Expect, LiveExpect
from agentops_evals.runner import LiveStop
from agentops_evals.scenarios import SCENARIOS, Env
from agentops_llm.hosted import GEMINI_FLASH_LITE, hosted_registry
from agentops_llm.litellm_provider import LiteLLMProvider
from agentops_llm.testing import stub_outcomes

QUOTA = LLMErrorCode.QUOTA_EXHAUSTED.value
LIMITED = LLMErrorCode.RATE_LIMITED.value


def _provider(outcomes: list[str]) -> tuple[LiteLLMProvider, list[int], list[float]]:
    completion, attempts = stub_outcomes(outcomes)
    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    provider = LiteLLMProvider(
        registry=hosted_registry(),
        completion=completion,
        budget_usd=100.0,
        total_budget_usd=100.0,
        sleep=sleep,
        cost_estimator=lambda model, prompt, completion: 0.1,
    )
    return provider, attempts, sleeps


def test_a_daily_quota_429_fails_once_as_quota_exhausted() -> None:
    provider, attempts, sleeps = _provider([QUOTA, "ok"])
    request = ModelRequest(run_id="r", messages=[Message(role="user", content="x")])
    with pytest.raises(LLMError) as raised:
        asyncio.run(provider.generate(request, GEMINI_FLASH_LITE))
    assert raised.value.code is LLMErrorCode.QUOTA_EXHAUSTED
    assert (len(attempts), sleeps, provider.retries("r")) == (1, [], 0)
    assert "PerDay" not in str(raised.value)  # the provider message is never recorded


def test_a_per_minute_429_is_still_retried() -> None:
    provider, attempts, sleeps = _provider([LIMITED, "ok"])
    request = ModelRequest(run_id="r", messages=[Message(role="user", content="x")])
    asyncio.run(provider.generate(request, GEMINI_FLASH_LITE))
    assert (len(attempts), sleeps) == (2, [10.0])


def _stopped(rule: LiveStop) -> tuple[str | None, str | None]:
    return rule.reason, rule.case_id


def test_stop_rule() -> None:
    rule = LiveStop(3)
    for case_id in ("a", "b"):
        rule.observe(case_id, [[LIMITED]])
    rule.observe("c", [[]])  # a success resets the streak
    assert (rule.streak, rule.reason) == (0, None)
    for case_id in ("d", "e", "f"):
        rule.observe(case_id, [[LIMITED]])
    assert (rule.reason, rule.case_id) == ("RATE_LIMITED in 3 consecutive cases", "f")
    quota = LiveStop(0)
    for case_id in ("a", "b", "c", "d"):
        quota.observe(case_id, [[LIMITED]])
    assert _stopped(quota) == (None, None)  # 0 disables the streak rule
    quota.observe("e", [[], [QUOTA]])
    assert _stopped(quota) == ("QUOTA_EXHAUSTED", "e")
    with pytest.raises(ValueError):
        LiveStop(-1)


# --- stubbed corpus and benchmark ---------------------------------------------------------


def _corpus(n: int) -> Corpus:
    workflows = [
        Case(
            id=f"wf-{i:02d}",
            category="normal",
            description="stubbed workflow",
            kind="workflow",
            task_text="Analyze synthetic sales",
            turns=[{"text": "mock answer"}],
            expect=Expect(status="completed"),
            live=LiveExpect(outcomes=["completed"]),
        )
        for i in range(1, n + 1)
    ]
    scenario = Case(
        id="scenario-01",
        category="reliability",
        description="deterministic scenario",
        kind="scenario",
        scenario="test",
        expect=Expect(tickets=0),
    )
    return Corpus(dataset_version="evals-test-v1", cases=[*workflows, scenario])


@pytest.fixture
def stubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    async def run(request: TaskRequest, deps: RunDependencies) -> RunDetail:
        status, errors = RunStatus.COMPLETED, []
        try:
            await deps.gateway.generate(
                ModelRequest(
                    run_id=request.run_id,
                    messages=[Message(role="user", content=request.task_text)],
                    max_output_tokens=10,
                )
            )
        except LLMError as exc:  # the real workflow turns model errors into a failed run
            status, errors = RunStatus.FAILED, [RunError(code=exc.code.value, message="stub")]
        return RunDetail(
            run_id=request.run_id,
            thread_id=f"thread-{request.run_id}",
            trace_id=deps.new_trace_id(),
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            task_text=request.task_text,
            status=status,
            llm_provider=deps.llm_provider,
            llm_model=deps.llm_model,
            llm_calls=1,
            errors=errors,
            policy_decisions=[PolicyDecision(subject="t", decision="allow", reason_code="ALLOWED")],
        )

    monkeypatch.setattr(runner, "run_task", run)
    monkeypatch.setattr(benchmark, "run_task", run)
    monkeypatch.setattr(Env, "tickets", lambda self, tenant, run_id: 0)
    monkeypatch.setitem(SCENARIOS, "test", lambda env, ctx: {"tickets": 0})


@pytest.mark.usefixtures("stubbed")
def test_corpus_stops_after_quota_exhausted_but_runs_scenarios() -> None:
    provider, attempts, _ = _provider(["ok", QUOTA])
    report = runner.run_corpus(_corpus(5), analytics_dsn="u", app_dsn="u", live_provider=provider)
    assert (report.stopped_early, report.stopped_after) == ("QUOTA_EXHAUSTED", "wf-02")
    assert report.not_run == ["wf-03", "wf-04", "wf-05"]
    assert [r.case_id for r in report.results] == ["wf-01", "wf-02", "scenario-01"]
    assert report.total == 3 and len(attempts) == 2
    assert report.live_scored == 2


@pytest.mark.usefixtures("stubbed")
def test_corpus_stops_after_three_rate_limited_cases_unless_disabled() -> None:
    provider, attempts, _ = _provider([LIMITED] * 12)
    report = runner.run_corpus(_corpus(6), analytics_dsn="u", app_dsn="u", live_provider=provider)
    assert report.stopped_early == "RATE_LIMITED in 3 consecutive cases"
    assert report.not_run == ["wf-04", "wf-05", "wf-06"]
    assert len(attempts) == 9  # three cases, each with its two retries

    provider, _, _ = _provider([LIMITED] * 18)
    report = runner.run_corpus(
        _corpus(6),
        analytics_dsn="u",
        app_dsn="u",
        live_provider=provider,
        stop_after_rate_limited=0,
    )
    assert (report.stopped_early, report.not_run) == (None, [])


@pytest.mark.usefixtures("stubbed")
def test_mock_corpus_never_stops() -> None:
    report = runner.run_corpus(_corpus(4), analytics_dsn="u", app_dsn="u")
    assert (report.stopped_early, report.not_run, report.total) == (None, [], 5)


@pytest.mark.usefixtures("stubbed")
def test_benchmark_stops_with_paired_runs(tmp_path: Path) -> None:
    provider, _, _ = _provider(["ok", "ok", "ok", QUOTA])
    report = benchmark.run_benchmark(
        _corpus(4), analytics_dsn="u", app_dsn="u", live_provider=provider
    )
    assert (report.stopped_early, report.stopped_after) == ("QUOTA_EXHAUSTED", "wf-02")
    assert report.not_run == ["wf-03", "wf-04"]
    assert report.sample_size == 2 and len(report.runs) == 4  # both designs for each run case
    _, md_path = benchmark.write_benchmark(report, tmp_path)
    assert "Stopped early: QUOTA_EXHAUSTED (after wf-02); 2 cases not run" in md_path.read_text(
        encoding="utf-8"
    )


@pytest.mark.usefixtures("stubbed")
def test_cli_reports_the_stop_and_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    provider, _, _ = _provider(["ok", QUOTA])
    monkeypatch.setattr(cli, "_live_provider", lambda budget, interval=0.0: provider)
    monkeypatch.setattr(cli, "load_corpus", lambda path: _corpus(4))
    monkeypatch.setenv("ANALYTICS_DATABASE_URL", "u")
    monkeypatch.setenv("APP_DATABASE_URL", "u")
    out = tmp_path / "live.json"
    argv: list[Any] = ["run", "--live", "--budget-usd", "5", "--out", str(out)]
    assert cli.main(argv) == 1
    printed = capsys.readouterr().out
    assert "STOPPED EARLY: QUOTA_EXHAUSTED after wf-02; 2 workflow cases not run" in printed
    assert out.exists()
    with pytest.raises(SystemExit):
        cli.main(
            [
                "run",
                "--live",
                "--budget-usd",
                "5",
                "--out",
                str(out),
                "--stop-after-rate-limited",
                "-1",
            ]
        )
