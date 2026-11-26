# Session Handoff

## Current Objective

- Goal: feat-024 (demo replays current and repeatable) on branch feat-024-replays, based on main a5d579c.
- Current status: feat-001 through feat-023 passing on main; feat-024 on this branch. The repository is public, with private vulnerability reporting on.
- Branch: feat-024-replays; landing on main needs owner approval. The other agent's worktree still has an empty branch feat-022-publication-prep; it can be dropped.

## Completed

- feat-020 and feat-021 landed on main (bd5d55e), both gates passing on the merged tree.
- feat-023 landed on main (c2235fa).
- feat-024 (session 031): run ids single-use with a checkpointer; recorder clears its replay threads; all replays re-recorded; replay page shows evidence gaps (D-021).
- feat-022 landed (a5d579c) and the repository was made public (session 030): no secrets in any commit; personal details removed from two notes; owner-named MIT license; SECURITY.md; docs/publishing.md; arch-107 rejects local machine paths (D-020).
- feat-023 (session 029): gateway PERMISSION_DENIED decisions become evidence gaps in the run detail and the report prompt; access-01 accepts abstention or a completion with the gap recorded (evals-v1.3.0, D-019).

## Verification

| Check | Result | Evidence |
|---|---|---|
| feat-024 gate | PASS, six layers incl. replay UI e2e | .harness/state/feat-024.json and trail |
| feat-022 gate | PASS, four layers at 7dca999 | .harness/state/feat-022.json and trail |
| feat-023 gate | PASS, five layers at 0f51fe2 | .harness/state/feat-023.json and trail |
| Mock corpus evals-v1.3.0 | 50/50 (integration suite) | testsuite/acceptance/feat_007 |
| Live corpus v1.2.0 at 92ac088 (feat-019) | live outcomes 37/41; no RATE_LIMITED | benchmarks/evals/v1.2/live-feat019/evals-live.json |

## Decisions

- D-021: run ids are single-use; resume_task is the only way to continue a run.
- D-020: publish without rewriting history; visibility and account settings stay with the owner.
- D-019: evidence gaps come from the gateway, never the model, and only whole tools are listed.

## Risks

- The combined live rerun (feat-018 + feat-019 + feat-021, now possibly feat-023) is still pending after the 2026-11-26 quota exhaustion; create the output folder before the corpus command.
- The scorer checks the recorded gap, not whether the summary's wording mentions it.
- Each replay recording changes the approved-ticket replay's approval id, ticket id and expiry.
- Live runs need the owner's `.env` (unreadable to the assistant); run them from the owner's terminal with fresh cap approval.
- Parallel agents allocate feature and session numbers independently; fetch origin/main before declaring the next feature.
- The architecture map is a snapshot through feat-015. ./init.sh remains unusable (D-004).

## Next Step

- Land feat-024 with owner approval. After the quota resets, run the combined live corpus and benchmark after the quota resets and compare with 37/41, including access-01's outcome and gap.
