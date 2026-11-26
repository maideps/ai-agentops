"""The versioned evaluation corpus (datasets/evals/<version>/cases.jsonl + manifest.json)."""

import json
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_CORPUS = Path("datasets/evals/v1")


class Expect(BaseModel):
    """What a case must show. Unset fields are not checked."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str | None = None
    abstain_reason: str | None = None
    declines: list[tuple[int, str]] | None = None
    analytics_absent: bool | None = None
    findings: int | None = None
    required_citations: list[str] = Field(default_factory=list)
    forbidden_evidence_prefixes: list[str] = Field(default_factory=list)
    denials: list[str] = Field(default_factory=list)
    error_codes: list[str] | None = None
    max_llm_calls: int | None = None
    # scenario observations
    reason: str | None = None
    outcome: str | None = None
    tickets: int | None = None
    executions: list[str] | None = None
    llm_calls_after_resume: int | None = None


LIVE_OUTCOMES = frozenset({"completed", "abstained", "rejected", "budget_exhausted"})


class LiveExpect(BaseModel):
    """How a hosted-model run of this case is scored (feat-016): by the answer's outcome, not the
    mock's scripted trajectory. Safety fields (forbidden evidence, tickets) come from ``Expect``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcomes: list[str] = Field(default_factory=list)
    unscored: bool = False
    declines_include: list[tuple[int, str]] = Field(default_factory=list)
    min_findings: int = Field(default=0, ge=0)
    cites_documents: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _outcomes_or_unscored(self) -> Self:
        if self.unscored == bool(self.outcomes):
            msg = "give acceptable outcomes or mark the case unscored, not both"
            raise ValueError(msg)
        if not set(self.outcomes) <= LIVE_OUTCOMES:
            msg = f"outcomes must be among {sorted(LIVE_OUTCOMES)}"
            raise ValueError(msg)
        return self


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    category: str
    description: str
    kind: Literal["workflow", "scenario"]
    expect: Expect
    tenant_id: str = "demo-a"
    user_id: str = "user-a-analyst"
    task_text: str = ""
    limits: dict[str, Any] = Field(default_factory=dict)
    turns: list[dict[str, Any]] = Field(default_factory=list)
    scenario: str | None = None
    live: LiveExpect | None = None


class Corpus(BaseModel):
    model_config = ConfigDict(frozen=True)

    dataset_version: str
    cases: list[Case]


def load_corpus(directory: Path = DEFAULT_CORPUS) -> Corpus:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    lines = (directory / "cases.jsonl").read_text(encoding="utf-8").splitlines()
    cases = [Case.model_validate_json(line) for line in lines if line.strip()]
    if len(cases) != manifest["cases"]:
        msg = f"manifest says {manifest['cases']} cases, file has {len(cases)}"
        raise ValueError(msg)
    return Corpus(dataset_version=manifest["dataset_version"], cases=cases)
