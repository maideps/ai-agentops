"""Orchestration benchmark (FR-016, NFR-008): single workflow vs. three specialists on the same
evaluation corpus, in mock mode.

What mock mode can measure: whether both orchestrations reach the expected outcome on every
workflow case, and their structural cost (model calls, tool calls, tokens, latency). What it
cannot measure: answer quality, because the model's replies are scripted. Hosted-model numbers
would need an explicitly opted-in, budget-capped live run and are not produced here.
"""

import json
import statistics
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import psycopg
from pydantic import BaseModel

from agentops_agents.state import RunDetail, RunLimits, TaskRequest
from agentops_agents.workflow import Orchestration, RunDependencies, prompt_version, run_task
from agentops_core.aio import run as run_async
from agentops_core.llm import LLMGateway
from agentops_evals.corpus import Case, Corpus
from agentops_evals.runner import _score_workflow, git_sha
from agentops_evals.scenarios import CountingProvider, Env
from agentops_llm.mock import MOCK_MODEL, MockLLMProvider, MockScript

BENCHMARK_VERSION = "orch-bench-v1.0.0"
ORCHESTRATIONS: tuple[Orchestration, ...] = ("single", "specialists")
LIMITATIONS = [
    "Mock mode: model replies are scripted per case, so answer quality is not compared; "
    "task success measures whether the platform reaches each case's expected outcome.",
    "Specialist scripts are derived mechanically from the baseline scripts (document calls to "
    "the research role, sales calls to the analyst role), so both see the same model intent.",
    "Tokens are a deterministic word-count estimate from the mock provider, not a tokenizer.",
    "Latency is local wall time including PostgreSQL; it varies between machines and runs.",
    "Cost is 0 in mock mode; no hosted model was called.",
    "Reliability and gateway-only scenarios are orchestration-independent and are excluded; "
    "the sample is the corpus's workflow cases.",
]


class Aggregate(BaseModel):
    cases: int
    task_success: int
    task_success_rate: float
    supported_finding_rate: float
    mean_llm_calls: float
    mean_tool_calls: float
    mean_tokens: float
    latency_ms_p50: float
    latency_ms_p95: float
    cost_usd_total: float


class CaseRun(BaseModel):
    case_id: str
    orchestration: Orchestration
    success: bool
    failures: list[str]
    status: str
    llm_calls: int
    tool_calls: int
    tokens: int
    findings_supported: int
    findings_checked: int
    latency_ms: float


class CaseRef(BaseModel):
    case_id: str
    category: str


class BenchmarkReport(BaseModel):
    benchmark_version: str
    dataset_version: str
    git_sha: str
    mode: Literal["mock"]
    provider: str
    model: str
    prompt_versions: dict[str, str]
    sample_size: int
    started_at: str
    cases: list[CaseRef]
    runs: list[CaseRun]
    aggregates: dict[str, Aggregate]
    recommendation: Literal["keep_single_workflow", "adopt_specialists"]
    rationale: str
    hosted_model_numbers: None = None
    limitations: list[str]

    def deterministic_view(self) -> dict[str, Any]:
        """Everything except timing, timestamps and the commit: what must reproduce."""
        runs = [r.model_dump(exclude={"latency_ms"}) for r in self.runs]
        aggregates = {
            k: v.model_dump(exclude={"latency_ms_p50", "latency_ms_p95"})
            for k, v in self.aggregates.items()
        }
        return {
            "benchmark_version": self.benchmark_version,
            "dataset_version": self.dataset_version,
            "prompt_versions": self.prompt_versions,
            "sample_size": self.sample_size,
            "runs": runs,
            "aggregates": aggregates,
            "recommendation": self.recommendation,
        }


def specialist_turns(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive a specialist script from a baseline script: the planning turn splits into a
    research turn (every non-sales call) and an analyst turn (sales calls); later turns (the
    report) are unchanged. A text or error planning turn is given to both roles."""
    if not turns:
        return []
    first, rest = turns[0], turns[1:]
    calls = first.get("tool_calls")
    if not calls:
        return [first, first, *rest]
    research = [c for c in calls if c["name"] != "get_sales_summary"]
    analyst = [c for c in calls if c["name"] == "get_sales_summary"]

    def turn(selected: list[dict[str, Any]], note: str) -> dict[str, Any]:
        return {"tool_calls": selected} if selected else {"text": note}

    return [turn(research, "No documents needed."), turn(analyst, "No sales data needed."), *rest]


def _run(env: Env, case: Case, orchestration: Orchestration, batch: str) -> CaseRun:
    run_id = f"bench-{case.id}-{orchestration[:4]}-{batch}"
    turns = case.turns if orchestration == "single" else specialist_turns(case.turns)
    provider = CountingProvider(
        MockLLMProvider(scripts=[MockScript.model_validate({"run_id": run_id, "turns": turns})])
    )
    trace_id = uuid.uuid4().hex
    deps = RunDependencies(
        gateway=LLMGateway(provider, MOCK_MODEL),
        llm_provider=provider.name,
        llm_model=MOCK_MODEL,
        connect=lambda: psycopg.connect(env.analytics_dsn),
        embedder=env.embedder,
        tool_gateway=env.gateway(),
        limits=RunLimits.model_validate(case.limits),
        new_trace_id=lambda: trace_id,
        orchestration=orchestration,
    )
    request = TaskRequest(
        run_id=run_id, tenant_id=case.tenant_id, user_id=case.user_id, task_text=case.task_text
    )
    started = time.perf_counter()
    detail: RunDetail = run_async(run_task(request, deps))
    latency_ms = (time.perf_counter() - started) * 1000
    # Outcome expectations only: call-count limits are written for the baseline and are what
    # this benchmark compares, so they are reported, not scored.
    expect = case.expect.model_copy(update={"max_llm_calls": None})
    tickets = env.tickets(case.tenant_id, run_id)
    failures = _score_workflow(expect, detail, provider.calls, tickets, trace_id)
    findings = [d for d in detail.policy_decisions if d.subject.startswith("finding:")]
    return CaseRun(
        case_id=case.id,
        orchestration=orchestration,
        success=not failures,
        failures=failures,
        status=detail.status.value,
        llm_calls=provider.calls,
        tool_calls=detail.tool_calls_executed,
        tokens=detail.prompt_tokens + detail.completion_tokens,
        findings_supported=sum(d.decision == "allow" for d in findings),
        findings_checked=len(findings),
        latency_ms=round(latency_ms, 1),
    )


def _aggregate(runs: list[CaseRun]) -> Aggregate:
    latencies = sorted(r.latency_ms for r in runs)
    checked = sum(r.findings_checked for r in runs)
    successes = sum(r.success for r in runs)
    return Aggregate(
        cases=len(runs),
        task_success=successes,
        task_success_rate=round(successes / len(runs), 4),
        supported_finding_rate=round(sum(r.findings_supported for r in runs) / checked, 4)
        if checked
        else 1.0,
        mean_llm_calls=round(statistics.fmean(r.llm_calls for r in runs), 3),
        mean_tool_calls=round(statistics.fmean(r.tool_calls for r in runs), 3),
        mean_tokens=round(statistics.fmean(r.tokens for r in runs), 1),
        latency_ms_p50=round(statistics.median(latencies), 1),
        latency_ms_p95=round(latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))], 1),
        cost_usd_total=0.0,
    )


def recommend(
    single: Aggregate, specialists: Aggregate
) -> tuple[Literal["keep_single_workflow", "adopt_specialists"], str]:
    """Adopt the specialists only if they reach strictly more expected outcomes; ties and losses
    keep the simpler design (spec M4.1)."""
    if specialists.task_success > single.task_success:
        return (
            "adopt_specialists",
            f"specialists reached {specialists.task_success}/{specialists.cases} expected "
            f"outcomes vs {single.task_success}/{single.cases} for the single workflow",
        )
    return (
        "keep_single_workflow",
        f"specialists reached {specialists.task_success}/{specialists.cases} expected outcomes "
        f"vs {single.task_success}/{single.cases}, so they do not measurably win; they cost "
        f"{specialists.mean_llm_calls:.2f} model calls and {specialists.mean_tokens:.0f} tokens "
        f"per run vs {single.mean_llm_calls:.2f} and {single.mean_tokens:.0f}",
    )


def run_benchmark(corpus: Corpus, *, analytics_dsn: str, app_dsn: str) -> BenchmarkReport:
    env = Env(analytics_dsn, app_dsn)
    batch = uuid.uuid4().hex[:6]
    cases = [c for c in corpus.cases if c.kind == "workflow"]
    started = datetime.now(UTC).isoformat()
    runs = [_run(env, case, orch, batch) for case in cases for orch in ORCHESTRATIONS]
    aggregates = {
        orch: _aggregate([r for r in runs if r.orchestration == orch]) for orch in ORCHESTRATIONS
    }
    recommendation, rationale = recommend(aggregates["single"], aggregates["specialists"])
    return BenchmarkReport(
        benchmark_version=BENCHMARK_VERSION,
        dataset_version=corpus.dataset_version,
        git_sha=git_sha(),
        mode="mock",
        provider="mock",
        model=MOCK_MODEL,
        prompt_versions={orch: prompt_version(orch) for orch in ORCHESTRATIONS},
        sample_size=len(cases),
        started_at=started,
        cases=[CaseRef(case_id=c.id, category=c.category) for c in cases],
        runs=runs,
        aggregates=aggregates,
        recommendation=recommendation,
        rationale=rationale,
        limitations=LIMITATIONS,
    )


def _markdown(report: BenchmarkReport) -> str:
    single, spec = report.aggregates["single"], report.aggregates["specialists"]
    rows = [
        (
            "Task success (expected outcome reached)",
            f"{single.task_success}/{single.cases}",
            f"{spec.task_success}/{spec.cases}",
        ),
        (
            "Supported findings (citation check)",
            f"{single.supported_finding_rate:.1%}",
            f"{spec.supported_finding_rate:.1%}",
        ),
        (
            "Model calls per run (mean)",
            f"{single.mean_llm_calls:.2f}",
            f"{spec.mean_llm_calls:.2f}",
        ),
        (
            "Tool calls per run (mean)",
            f"{single.mean_tool_calls:.2f}",
            f"{spec.mean_tool_calls:.2f}",
        ),
        ("Tokens per run (mean, estimate)", f"{single.mean_tokens:.0f}", f"{spec.mean_tokens:.0f}"),
        (
            "Latency p50 / p95 (ms, local)",
            f"{single.latency_ms_p50:.0f} / {single.latency_ms_p95:.0f}",
            f"{spec.latency_ms_p50:.0f} / {spec.latency_ms_p95:.0f}",
        ),
        ("Cost (USD)", f"{single.cost_usd_total:.2f}", f"{spec.cost_usd_total:.2f}"),
    ]
    differing = [
        (a.case_id, a.success, b.success)
        for a, b in zip(
            [r for r in report.runs if r.orchestration == "single"],
            [r for r in report.runs if r.orchestration == "specialists"],
            strict=True,
        )
        if a.success != b.success
    ]
    lines = [
        "# Orchestration benchmark: single workflow vs. specialists",
        "",
        f"- Benchmark: {report.benchmark_version}",
        f"- Dataset: {report.dataset_version}",
        f"- Commit: {report.git_sha}",
        f"- Mode: {report.mode} (provider {report.provider}, model {report.model});"
        " hosted-model numbers: none",
        f"- Prompt versions: single {report.prompt_versions['single']},"
        f" specialists {report.prompt_versions['specialists']}",
        f"- Sample size: {report.sample_size} workflow cases, each run once per orchestration",
        "",
        "| Metric | Single workflow | Specialists |",
        "|---|---|---|",
        *[f"| {name} | {a} | {b} |" for name, a, b in rows],
        "",
        f"**Recommendation: {report.recommendation}.**"
        f" {report.rationale[0].upper()}{report.rationale[1:]}.",
        "",
        "Cases where the orchestrations differ: "
        + (
            ", ".join(
                f"{cid} (single {'pass' if a else 'fail'}, specialists {'pass' if b else 'fail'})"
                for cid, a, b in differing
            )
            or "none"
        )
        + ".",
        "",
        "## Limitations",
        "",
        *[f"- {item}" for item in report.limitations],
        "",
    ]
    return "\n".join(lines)


def write_benchmark(report: BenchmarkReport, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"results-{report.mode}.json"
    md_path = out_dir / "REPORT.md"
    json_path.write_bytes((json.dumps(report.model_dump(mode="json"), indent=2) + "\n").encode())
    md_path.write_bytes(_markdown(report).encode("utf-8"))
    return json_path, md_path
