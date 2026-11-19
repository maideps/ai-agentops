"""Deterministic policy checks. The model proposes; this module decides (spec section 9)."""

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ValidationError

from agentops_agents.state import PolicyDecision, Report
from agentops_agents.tools import ToolSpec
from agentops_core.llm import ToolCall


def authorize_tool_calls(
    calls: Sequence[ToolCall], allowlist: Mapping[str, ToolSpec]
) -> tuple[list[tuple[ToolCall, BaseModel]], list[PolicyDecision]]:
    """Allow only allowlisted tools with schema-valid arguments; everything else is denied."""
    allowed: list[tuple[ToolCall, BaseModel]] = []
    decisions: list[PolicyDecision] = []
    for call in calls:
        subject = f"tool_call:{call.id}:{call.name}"
        spec = allowlist.get(call.name)
        if spec is None:
            decisions.append(
                PolicyDecision(subject=subject, decision="deny", reason_code="TOOL_NOT_ALLOWED")
            )
            continue
        try:
            args = spec.args_model.model_validate(call.arguments)
        except ValidationError:
            decisions.append(
                PolicyDecision(subject=subject, decision="deny", reason_code="INVALID_ARGUMENTS")
            )
            continue
        decisions.append(
            PolicyDecision(subject=subject, decision="allow", reason_code="ALLOWLISTED")
        )
        allowed.append((call, args))
    return allowed, decisions


def enforce_citations(
    report: Report, usable_evidence_ids: set[str]
) -> tuple[Report, list[PolicyDecision]]:
    """Drop findings that cite anything the run did not give the model (FR-012)."""
    kept = []
    decisions: list[PolicyDecision] = []
    for index, finding in enumerate(report.findings):
        subject = f"finding:{index}"
        if set(finding.citations) <= usable_evidence_ids:
            kept.append(finding)
            decisions.append(
                PolicyDecision(subject=subject, decision="allow", reason_code="CITATIONS_SUPPORTED")
            )
        else:
            decisions.append(
                PolicyDecision(subject=subject, decision="deny", reason_code="UNSUPPORTED_CITATION")
            )
    return report.model_copy(update={"findings": kept}), decisions
