"""Opted-in evaluation uses the hosted adapter, records costs, and preserves mock defaults."""

from pathlib import Path

import pytest

from agentops_agents.state import PolicyDecision, RunDetail, RunStatus, TaskRequest
from agentops_agents.workflow import RunDependencies
from agentops_core.llm import Message, ModelRequest
from agentops_evals import __main__ as cli
from agentops_evals import benchmark, runner
from agentops_evals.corpus import Case, Corpus, Expect
from agentops_evals.scenarios import SCENARIOS, Env
from agentops_llm.hosted import GEMINI_FLASH_LITE, hosted_registry
from agentops_llm.litellm_provider import LiteLLMProvider
from agentops_llm.testing import stub_completion

CANARY = "CANARY-SECRET-0008"


@pytest.fixture
def corpus() -> Corpus:
    return Corpus(
        dataset_version="evals-test-v1",
        cases=[
            Case(
                id="normal-01",
                category="normal",
                description="one workflow",
                kind="workflow",
                task_text="Analyze synthetic sales",
                turns=[{"text": "mock answer"}],
                expect=Expect(status="completed"),
            ),
            Case(
                id="scenario-01",
                category="reliability",
                description="one deterministic gateway scenario",
                kind="scenario",
                scenario="test",
                expect=Expect(tickets=0),
            ),
        ],
    )


@pytest.fixture
def workflow(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    models: list[str] = []

    async def run(request: TaskRequest, deps: RunDependencies) -> RunDetail:
        models.append(deps.llm_model)
        response = await deps.gateway.generate(
            ModelRequest(
                run_id=request.run_id,
                messages=[Message(role="user", content=request.task_text)],
                max_output_tokens=10,
            )
        )
        return RunDetail(
            run_id=request.run_id,
            thread_id=f"thread-{request.run_id}",
            trace_id=deps.new_trace_id(),
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            task_text=request.task_text,
            status=RunStatus.COMPLETED,
            llm_provider=deps.llm_provider,
            llm_model=deps.llm_model,
            llm_calls=1,
            prompt_tokens=response.prompt_tokens or 0,
            completion_tokens=response.completion_tokens or 0,
            policy_decisions=[
                PolicyDecision(subject="test", decision="allow", reason_code="ALLOWED")
            ],
        )

    monkeypatch.setattr(runner, "run_task", run)
    monkeypatch.setattr(benchmark, "run_task", run)
    monkeypatch.setattr(Env, "tickets", lambda self, tenant, run_id: 0)
    monkeypatch.setitem(SCENARIOS, "test", lambda env, ctx: {"tickets": 0})
    return models


def _provider() -> LiteLLMProvider:
    return LiteLLMProvider(
        registry=hosted_registry(),
        completion=stub_completion([{"text": "hosted answer"}] * 2),
        budget_usd=1.0,
        total_budget_usd=1.0,
        cost_estimator=lambda model, prompt, completion: 0.1,
    )


def test_corpus_uses_live_workflows_but_labels_mock_scenarios(
    corpus: Corpus, workflow: list[str]
) -> None:
    report = runner.run_corpus(
        corpus, analytics_dsn="unused", app_dsn="unused", live_provider=_provider()
    )
    assert workflow == [GEMINI_FLASH_LITE]
    assert report.mode == "live"
    assert report.dataset_version == corpus.dataset_version
    assert report.git_sha and report.prompt_version
    assert report.provider == "gemini" and report.model == GEMINI_FLASH_LITE
    assert report.cost_usd_total == 0.1
    assert report.reserved_usd_total == 0.1
    assert [r.observed["model_mode"] for r in report.results] == ["live", "mock"]
    assert report.limitations


def test_benchmark_runs_both_designs_live_and_keeps_costs(
    corpus: Corpus, workflow: list[str], tmp_path: Path
) -> None:
    report = benchmark.run_benchmark(
        corpus, analytics_dsn="unused", app_dsn="unused", live_provider=_provider()
    )
    assert workflow == [GEMINI_FLASH_LITE, GEMINI_FLASH_LITE]
    assert report.mode == "live"
    assert report.sample_size == 1
    assert set(report.prompt_versions) == {"single", "specialists"}
    assert report.aggregates["single"].cost_usd_total == 0.1
    assert report.aggregates["specialists"].cost_usd_total == 0.1
    assert report.hosted_model_numbers == {"cost_usd_total": 0.2, "reserved_usd_total": 0.2}
    json_path, md_path = benchmark.write_benchmark(report, tmp_path)
    assert json_path.name == "results-live.json"
    assert "hosted-model numbers: none" not in md_path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "mode, enabled",
    [("mock", "true"), ("replay", "true"), ("hosted_free", "false"), ("live_paid", "false")],
)
def test_cli_live_opt_in_requires_both_environment_flags(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mode: str,
    enabled: str,
) -> None:
    monkeypatch.setenv("LLM_MODE", mode)
    monkeypatch.setenv("ENABLE_LIVE_LLM", enabled)
    monkeypatch.setenv("GEMINI_API_KEY", CANARY)
    assert cli.main(["run", "--live", "--budget-usd", "1", "--out", "unused.json"]) == 2
    assert "PROVIDER_UNAVAILABLE" in capsys.readouterr().err


def test_cli_with_a_key_and_live_environment_still_defaults_to_mock(
    monkeypatch: pytest.MonkeyPatch, corpus: Corpus, workflow: list[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("LLM_MODE", "live_paid")
    monkeypatch.setenv("ENABLE_LIVE_LLM", "true")
    monkeypatch.setenv("GEMINI_API_KEY", CANARY)
    monkeypatch.setenv("ANALYTICS_DATABASE_URL", "unused")
    monkeypatch.setenv("APP_DATABASE_URL", "unused")
    monkeypatch.setattr(cli, "load_corpus", lambda directory: corpus)
    out = tmp_path / "report.json"
    assert cli.main(["run", "--out", str(out)]) == 0
    assert workflow == ["mock-deterministic-v1"]
    assert CANARY not in out.read_text(encoding="utf-8")
    assert '"mode": "mock"' in out.read_text(encoding="utf-8")


@pytest.mark.parametrize("budget", ["nan", "inf", "-1", "0"])
def test_cli_rejects_unbounded_or_zero_live_budgets(budget: str) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(["run", "--live", "--budget-usd", budget, "--out", "unused.json"])
    assert raised.value.code == 2


def test_cli_failed_live_benchmark_preserves_results_and_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, corpus: Corpus, workflow: list[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("ANALYTICS_DATABASE_URL", "unused")
    monkeypatch.setenv("APP_DATABASE_URL", "unused")
    monkeypatch.setattr(cli, "_live_provider", lambda budget: _provider())
    broken = corpus.cases[0].model_copy(update={"expect": Expect(status="abstained")})
    monkeypatch.setattr(
        cli, "load_corpus", lambda directory: corpus.model_copy(update={"cases": [broken]})
    )
    assert cli.main(["benchmark", "--live", "--budget-usd", "1", "--out-dir", str(tmp_path)]) == 1
    assert (tmp_path / "results-live.json").is_file()
    assert workflow == [GEMINI_FLASH_LITE, GEMINI_FLASH_LITE]


@pytest.mark.integration
def test_real_workflow_corpus_and_benchmark_use_budgeted_hosted_adapter(
    seeded_db: str, analytics_dsn: str, app_dsn: str
) -> None:
    from agentops_evals.corpus import load_corpus

    corpus = load_corpus()
    case = next(c for c in corpus.cases if c.id == "normal-01")
    selected = corpus.model_copy(update={"cases": [case]})

    def provider(turns: list[dict[str, object]]) -> LiteLLMProvider:
        return LiteLLMProvider(
            registry=hosted_registry(),
            completion=stub_completion(turns),
            budget_usd=3.0,
            total_budget_usd=3.0,
        )

    report = runner.run_corpus(
        selected,
        analytics_dsn=analytics_dsn,
        app_dsn=app_dsn,
        live_provider=provider(case.turns),
    )
    assert report.passed == 1, report.results[0].failures
    assert 0 < report.cost_usd_total < report.reserved_usd_total <= 3.0
    bench = benchmark.run_benchmark(
        selected,
        analytics_dsn=analytics_dsn,
        app_dsn=app_dsn,
        live_provider=provider([*case.turns, *benchmark.specialist_turns(case.turns)]),
    )
    assert all(r.success for r in bench.runs), [r.failures for r in bench.runs]
    assert all(0 < r.cost_usd < r.reserved_usd <= 3.0 for r in bench.runs)
