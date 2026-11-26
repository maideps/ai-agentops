# Session Handoff

## Current Objective

- Goal: feat-022 (repository ready to be public) on branch feat-022-publication, based on main c2235fa. This session took feat-022 over from the other agent, which could not continue.
- Current status: feat-001 through feat-021 and feat-023 passing on main; feat-022 on this branch.
- Branch: feat-022-publication; landing on main needs owner approval. The other agent's worktree still has an empty branch feat-022-publication-prep; it can be dropped.

## Completed

- feat-020 and feat-021 landed on main (bd5d55e), both gates passing on the merged tree.
- feat-023 landed on main (c2235fa).
- feat-022 (session 030): no secrets in any commit; personal details removed from two notes; owner-named MIT license; SECURITY.md; docs/publishing.md; arch-107 rejects local machine paths (D-020).
- feat-023 (session 029): gateway PERMISSION_DENIED decisions become evidence gaps in the run detail and the report prompt; access-01 accepts abstention or a completion with the gap recorded (evals-v1.3.0, D-019).

## Verification

| Check | Result | Evidence |
|---|---|---|
| feat-022 gate | See .harness/state/feat-022.json | .harness/state/feat-022.json and trail |
| feat-023 gate | PASS, five layers at 0f51fe2 | .harness/state/feat-023.json and trail |
| Mock corpus evals-v1.3.0 | 50/50 (integration suite) | testsuite/acceptance/feat_007 |
| Live corpus v1.2.0 at 92ac088 (feat-019) | live outcomes 37/41; no RATE_LIMITED | benchmarks/evals/v1.2/live-feat019/evals-live.json |

## Decisions

- D-020: publish without rewriting history; visibility and account settings stay with the owner.
- D-019: evidence gaps come from the gateway, never the model, and only whole tools are listed.

## Risks

- The combined live rerun (feat-018 + feat-019 + feat-021, now possibly feat-023) is still pending after the 2026-11-26 quota exhaustion; create the output folder before the corpus command.
- The scorer checks the recorded gap, not whether the summary's wording mentions it.
- Demo replays other than the sample predate feat-014, feat-018 and feat-023.
- Live runs need the owner's `.env` (unreadable to the assistant); run them from the owner's terminal with fresh cap approval.
- Parallel agents allocate feature and session numbers independently; fetch origin/main before declaring the next feature.
- The architecture map is a snapshot through feat-015. ./init.sh remains unusable (D-004).

## Next Step

- Land feat-022 with owner approval; the owner then changes the GitHub settings listed in docs/publishing.md. After the quota resets, run the combined live corpus and benchmark after the quota resets and compare with 37/41, including access-01's outcome and gap.
