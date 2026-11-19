"""Run the corpus in mock mode and score every case (NFR-002, NFR-006, NFR-007).

Each case runs inside an ``eval.case`` span whose trace id is also the run's trace id, so a
failing case leads straight to its spans. The report records dataset_version, git_sha, model,
prompt_version and policy_version.
"""

import hashlib
import os
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from pydantic import BaseModel, Field

from agentops_agents.state import RunDetail, RunLimits, TaskRequest
from agentops_agents.workflow import PLAN_PROMPT, REPORT_PROMPT, RunDependencies, run_task
from agentops_core.aio import run as run_async
from agentops_core.llm import LLMGateway
from agentops_core.policy import POLICY_VERSION
from agentops_evals.corpus import Case, Corpus, Expect
from agentops_evals.scenarios import SCENARIOS, CountingProvider, Env
from agentops_llm.mock import MOCK_MODEL, MockLLMProvider, MockScript
from agentops_telemetry.tracing import span
from agentops_tools.gateway import CallContext

PROMPT_VERSION = hashlib.sha256((PLAN_PROMPT + "\n" + REPORT_PROMPT).encode()).hexdigest()[:12]


class CaseResult(BaseModel):
    case_id: str
    category: str
    kind: str
    passed: bool
    failures: list[str]
    run_id: str
    trace_id: str
    status: str | None = None
    observed: dict[str, Any] = Field(default_factory=dict)


class EvalReport(BaseModel):
    dataset_version: str
    git_sha: str
    provider: str
    model: str
    prompt_version: str
    policy_version: str
    started_at: str
    finished_at: str
    total: int
    passed: int
    failed: int
    by_category: dict[str, dict[str, int]]
    results: list[CaseResult]


def git_sha(root: Path = Path()) -> str:
    """The commit under evaluation, from CI's GITHUB_SHA or the .git directory (no subprocess)."""
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    head = root / ".git" / "HEAD"
    if not head.exists():
        return "unknown"
    ref = head.read_text(encoding="utf-8").strip()
    if not ref.startswith("ref: "):
        return ref
    name = ref.removeprefix("ref: ")
    loose = root / ".git" / name
    if loose.exists():
        return loose.read_text(encoding="utf-8").strip()
    packed = root / ".git" / "packed-refs"
    if packed.exists():
        for line in packed.read_text(encoding="utf-8").splitlines():
            if line.endswith(" " + name):
                return line.split(" ", 1)[0]
    return "unknown"


def _workflow(env: Env, case: Case, run_id: str, trace_id: str) -> tuple[RunDetail, int]:
    script = MockScript.model_validate({"run_id": run_id, "turns": case.turns})
    provider = CountingProvider(MockLLMProvider(scripts=[script]))
    deps = RunDependencies(
        gateway=LLMGateway(provider, MOCK_MODEL),
        llm_provider=provider.name,
        llm_model=MOCK_MODEL,
        connect=lambda: psycopg.connect(env.analytics_dsn),
        embedder=env.embedder,
        tool_gateway=env.gateway(),
        limits=RunLimits.model_validate(case.limits),
        new_trace_id=lambda: trace_id,
    )
    request = TaskRequest(
        run_id=run_id, tenant_id=case.tenant_id, user_id=case.user_id, task_text=case.task_text
    )
    return run_async(run_task(request, deps)), provider.calls


def _score_workflow(
    expect: Expect, detail: RunDetail, calls: int, tickets: int, trace_id: str
) -> list[str]:
    failures: list[str] = []

    def check(ok: bool, message: str) -> None:
        if not ok:
            failures.append(message)

    # Invariants for every evaluated workflow (NFR-002).
    check(detail.trace_id == trace_id, f"trace id {detail.trace_id} != {trace_id}")
    check(bool(detail.policy_decisions), "no policy decision recorded")
    if expect.status is not None:
        check(
            detail.status.value == expect.status, f"status {detail.status.value} != {expect.status}"
        )
    if expect.abstain_reason is not None:
        check(
            detail.abstain_reason == expect.abstain_reason,
            f"abstain_reason {detail.abstain_reason} != {expect.abstain_reason}",
        )
    if expect.declines is not None:
        got = (
            [(r.product_id, r.region) for r in detail.analytics.declines]
            if detail.analytics
            else None
        )
        check(got == [tuple(d) for d in expect.declines], f"declines {got} != {expect.declines}")
    if expect.analytics_absent:
        check(detail.analytics is None, "analytics present")
    findings = detail.report.findings if detail.report else []
    if expect.findings is not None:
        check(len(findings) == expect.findings, f"findings {len(findings)} != {expect.findings}")
    cited = {c for f in findings for c in f.citations}
    for citation in expect.required_citations:
        check(citation in cited, f"missing citation {citation}")
    for prefix in expect.forbidden_evidence_prefixes:
        leaked = [e.id for e in detail.evidence if e.id.startswith(prefix)]
        check(not leaked, f"forbidden evidence {leaked}")
    denied = Counter(d.reason_code for d in detail.policy_decisions if d.decision == "deny")
    for reason, count in Counter(expect.denials).items():
        check(
            denied[reason] >= count, f"denial {reason} x{count} not recorded (got {dict(denied)})"
        )
    if expect.error_codes is not None:
        codes = [e.code for e in detail.errors]
        check(codes == expect.error_codes, f"errors {codes} != {expect.error_codes}")
    if expect.max_llm_calls is not None:
        check(calls <= expect.max_llm_calls, f"{calls} model calls > {expect.max_llm_calls}")
    if expect.tickets is not None:
        check(tickets == expect.tickets, f"tickets {tickets} != {expect.tickets}")
    return failures


def _score_scenario(expect: Expect, observed: dict[str, Any]) -> list[str]:
    failures = []
    for name in ("reason", "outcome", "tickets", "executions", "status", "llm_calls_after_resume"):
        wanted = getattr(expect, name)
        if wanted is not None and observed.get(name) != wanted:
            failures.append(f"{name} {observed.get(name)!r} != {wanted!r}")
    return failures


def run_case(env: Env, case: Case, batch: str) -> CaseResult:
    run_id = f"eval-{case.id}-{batch}"
    trace_id = uuid.uuid4().hex
    attrs = {"eval.case_id": case.id, "eval.category": case.category, "agentops.run_id": run_id}
    with span("eval.case", attrs, trace_id=trace_id) as current:
        if case.kind == "workflow":
            detail, calls = _workflow(env, case, run_id, trace_id)
            tickets = env.tickets(case.tenant_id, run_id)
            failures = _score_workflow(case.expect, detail, calls, tickets, trace_id)
            status: str | None = detail.status.value
            observed: dict[str, Any] = {"llm_calls": calls, "tickets": tickets}
        else:
            ctx = CallContext(tenant_id=case.tenant_id, user_id=case.user_id, run_id=run_id)
            observed = SCENARIOS[str(case.scenario)](env, ctx)
            failures = _score_scenario(case.expect, observed)
            status = observed.get("status")
        current.set_attribute("eval.passed", not failures)
    return CaseResult(
        case_id=case.id,
        category=case.category,
        kind=case.kind,
        passed=not failures,
        failures=failures,
        run_id=run_id,
        trace_id=trace_id,
        status=status,
        observed=observed,
    )


def run_corpus(
    corpus: Corpus, *, analytics_dsn: str, app_dsn: str, only: set[str] | None = None
) -> EvalReport:
    env = Env(analytics_dsn, app_dsn)
    batch = uuid.uuid4().hex[:8]  # run ids stay unique across repeated evaluations
    started = datetime.now(UTC).isoformat()
    results = [run_case(env, c, batch) for c in corpus.cases if only is None or c.id in only]
    by_category: dict[str, dict[str, int]] = {}
    for result in results:
        bucket = by_category.setdefault(result.category, {"total": 0, "passed": 0})
        bucket["total"] += 1
        bucket["passed"] += int(result.passed)
    passed = sum(r.passed for r in results)
    return EvalReport(
        dataset_version=corpus.dataset_version,
        git_sha=git_sha(),
        provider="mock",
        model=MOCK_MODEL,
        prompt_version=PROMPT_VERSION,
        policy_version=POLICY_VERSION,
        started_at=started,
        finished_at=datetime.now(UTC).isoformat(),
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        by_category=by_category,
        results=results,
    )
