# Session Handoff

## Current Objective

- Goal: feat-021 (live evaluation stops when the provider quota runs out) closed on branch feat-021-quota-stop. No feature is active on it.
- Current status: feat-001 through feat-019 and feat-021 passing; feat-020 (retrieval comparison, session 027) is on another agent's branch and not on main yet.
- Branch: feat-021-quota-stop, based on main c2827a3; landing needs owner approval and should follow or merge feat-020 so session numbering stays complete.

## Completed

- feat-021 (session 028): per-day quota 429 → QUOTA_EXHAUSTED, never retried; live corpus and benchmark stop early (first QUOTA_EXHAUSTED or 3 consecutive rate-limited cases), record not-run cases and exit 1 (D-016 amendment 4).

## Verification

| Check | Result | Evidence |
|---|---|---|
| feat-021 gate | PASS, five layers | .harness/state/feat-021.json and trail |
| Regressions | npm run check exit 0; 171 offline, 132 integration, nine UI e2e | Offline only; no live calls |

## Decisions

- D-016 amendment 4: daily-quota 429s fail at once; live batches stop early with not-run cases recorded.

## Risks

- The combined live rerun (feat-018 + feat-019 + feat-021) is still pending after the 2026-11-26 quota exhaustion; create benchmarks/evals/v1.2/live-merged-018-019 before the corpus command.
- Daily-quota detection depends on the provider naming a per-day quota; the streak rule is the fallback.
- access-01 expects abstention, but a viewer's run may complete from permitted documents (no sales leak).
- Session 027 (feat-020) is not on this branch, so the harness lint reports it missing until feat-020 lands or is merged.
- Live runs need the owner's `.env` (unreadable to the assistant); run them from the owner's terminal with fresh cap approval.
- Parallel agents allocate feature and session numbers independently; fetch origin/main before declaring the next feature.
- The architecture map is a snapshot through feat-015. ./init.sh remains unusable (D-004).

## Next Step

- Land feat-021 after (or merged with) feat-020, then run the combined live corpus and benchmark after the quota resets and compare with 37/41.
