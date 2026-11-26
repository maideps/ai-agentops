# Session Handoff

## Current Objective

- feat-018: policy-aware report citation guidance, passing on feat-018-policy-report-citations.
- Base ed5c27d; feat-001 through feat-018 passing, none active.
- Work is isolated in the previously owned retrieval worktree. Original checkout untouched.

## Completed

- Added policy guidance only when document evidence survives the existing report context limit.
- List only included document IDs and ask relevant policy-backed findings to cite their
  supporting passages alongside sales evidence when needed. Forbid invented policy
  claims and unsupported citations. No-document prompts remain unchanged.
- Both orchestrations reuse the shared report node; the new template participates in
  prompt_version. Ranking, selection, report schema, citation enforcement and provider
  retries/budget reservations remain unchanged.
- Added captured-request tests and real single/specialist workflow acceptance using
  existing scripted providers. Updated README, spec, architecture and limitations.

## Verification

- Baseline full check PASS: 146 offline tests, nine UI e2e and strict mypy over 113 sources.
- New tests reproduced three missing-guidance/provenance failures before product edits.
- Final full check PASS: 153 offline tests, nine UI e2e, strict mypy over 114 sources,
  14 architecture rules and production build. All 132 isolated integration tests pass,
  including both new workflow paths and corpus/benchmark regressions.
- Isolated database: agentops_feat018_test; use its AGENTOPS_TEST_* URLs, not another
  session's database. GITHUB_SHA must be actual HEAD in a linked worktree.
- All four feat-018 gate layers PASS at committed bab2cce, including nine focused
  acceptance cases. Bound state/trail recorded; final clean-check/session-end follow
  the evidence commit. Optional unconfigured framework checks report SKIP.

## Decisions and Risks

- Documents are not necessarily policy documents: guidance is conditional on relevance/support,
  not a requirement to add a policy finding to every report.
- Citation enforcement still checks included identifiers, not semantic entailment.
  Offline tests verify the request, not hosted compliance or quality.
- Existing live reports, mock benchmark and other replay artifacts remain historical
  evidence; none measures this prompt. The deterministic sample replay was rerecorded
  with its existing test hook: only mock prompt_tokens changes 308 to 366, all report
  content/citations/outcomes unchanged. No new hosted calls or spend.
- Free-tier 429s remain unretried and may dominate future live comparisons.
- The architecture map remains a historical snapshot through feat-015.
- ./init.sh remains unusable (D-004); use the brief and npm check.

## Next Step

Obtain separate approval before pushing/merging this passing branch. Fetch remote
main before any approved publication to detect feature/session allocation collisions.
No hosted call is authorized; a later quality comparison needs fresh owner-approved
caps. Rate-limit handling is separate scope. See progress/025-2026-11-26.md.
