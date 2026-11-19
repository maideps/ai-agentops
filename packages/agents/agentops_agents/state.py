"""Typed run state, limits, report schema and the run detail returned to callers."""

from enum import StrEnum
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from agentops_core.policy import POLICY_VERSION as POLICY_VERSION

# Result types live with the tools; re-exported for the run detail's callers.
from agentops_tools.read_tools import DeclineRow as DeclineRow
from agentops_tools.read_tools import Evidence as Evidence
from agentops_tools.read_tools import SalesAnalytics as SalesAnalytics


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RunStatus(StrEnum):
    COMPLETED = "completed"
    ABSTAINED = "abstained"
    REJECTED = "rejected"
    BUDGET_EXHAUSTED = "budget_exhausted"
    TIMED_OUT = "timed_out"
    FAILED = "failed"
    AWAITING_APPROVAL = "awaiting_approval"


class RunLimits(_Model):
    """Per-run limits (FR-011). Defaults mirror the documented .env.example values."""

    max_llm_calls: int = Field(default=6, ge=0)
    max_tool_calls: int = Field(default=8, ge=0)
    max_graph_steps: int = Field(default=16, ge=1)
    max_run_seconds: float = Field(default=90, gt=0)
    max_output_tokens: int = Field(default=500, ge=1)
    max_context_tokens: int = Field(default=1500, ge=1)


class TaskRequest(_Model):
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    tenant_id: str
    user_id: str
    task_text: str = Field(min_length=1, max_length=2000)
    # Propose a follow-up ticket and pause for human approval (needs a checkpointer).
    propose_followup: bool = False


class Finding(_Model):
    claim: str = Field(min_length=1, max_length=600)
    citations: list[str] = Field(min_length=1, max_length=10)


class Report(_Model):
    summary: str = Field(min_length=1, max_length=2000)
    findings: list[Finding] = Field(max_length=10)


class PolicyDecision(_Model):
    subject: str
    decision: Literal["allow", "deny"]
    reason_code: str
    policy_version: str = POLICY_VERSION


class RunError(_Model):
    code: str
    message: str


class ContextWindow(_Model):
    included_evidence_ids: list[str] = Field(default_factory=list)
    dropped_evidence_ids: list[str] = Field(default_factory=list)
    estimated_tokens: int = 0


class RunDetail(_Model):
    """Sanitized result of one run: what was asked, decided, used and produced (FR-013 seed)."""

    run_id: str
    thread_id: str
    trace_id: str
    tenant_id: str
    user_id: str
    task_text: str
    status: RunStatus
    abstain_reason: str | None = None
    report: Report | None = None
    analytics: SalesAnalytics | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    context: ContextWindow = Field(default_factory=ContextWindow)
    policy_decisions: list[PolicyDecision] = Field(default_factory=list)
    errors: list[RunError] = Field(default_factory=list)
    llm_provider: str
    llm_model: str
    llm_calls: int = 0
    tool_calls_executed: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    proposed_action: dict[str, Any] | None = None
    action_result: dict[str, Any] | None = None


class AgentRunState(TypedDict, total=False):
    """LangGraph state: JSON-compatible values only, no credentials, no connections."""

    run_id: str
    trace_id: str
    tenant_id: str
    user_id: str
    task_text: str
    proposed_tool_calls: list[dict[str, object]]
    authorized_tool_calls: list[dict[str, object]]
    analytics: dict[str, object] | None
    evidence: list[dict[str, object]]
    context: dict[str, object]
    draft_report: dict[str, object] | None
    report: dict[str, object] | None
    policy_decisions: list[dict[str, object]]
    errors: list[dict[str, object]]
    llm_calls: int
    tool_calls_executed: int
    prompt_tokens: int
    completion_tokens: int
    status: str
    abstain_reason: str | None
    thread_id: str
    propose_followup: bool
    sales_executed: bool
    proposed_action: dict[str, object] | None
    approval_decision: bool | None
    action_result: dict[str, object] | None
