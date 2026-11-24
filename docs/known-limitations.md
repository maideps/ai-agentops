# Known limitations

What AI AgentOps does not do or has not shown yet, as of feat-013. Each item names the decision record that explains it.

## Evidence and measurement

- **No hosted quality baseline yet.** Tests, replays and the default corpus/benchmark use scripted replies. Two free-tier Gemini 3.5 Flash-Lite runs exist. In the first, the model invented quarters and abstained; after feat-014 (D-017) it plans with real quarters, but most report-writing calls failed on provider overload or network outages, so answer quality is still effectively unmeasured (D-011, D-012, D-016, D-017).
- **Live expectations still follow mock trajectories.** After feat-015, 22 of 42 live workflows complete, yet the corpus stays at 11/50: most remaining checks expect exact decline counts, specific policy denials or scripted errors. Live reports do not yet record each failed case's error code. The live benchmark's "adopt_specialists" (4/42 vs 2/42, one run each) is noise, not a design decision (D-012).
- **Provider overload and throttling can still fail a case.** A 503 or connection error gets at most two budget-reserved retries (feat-015); a third failure, a timeout or a rate limit ends the case as failed. Each retry reserves about USD 0.32, so long outages exhaust caps faster. Model availability can also change: `gemini-2.5-flash-lite` was withdrawn for new users and replaced (D-016 amendment).
- **Budget reservations are conservative and process-local.** Each call reserves the full input window plus bounded output, with no refund. A small budget may refuse even a short prompt. Prices and token ceilings come from the bundled SDK map, not an invoice or provider-enforced account limit; persistent account-wide budgets remain unimplemented (D-016).
- **Live evaluation is not a replacement quality corpus.** Gateway/reliability scenarios stay mocked, and workflow expectations include scripted errors/trajectories that a real model may not produce. Reports preserve those failures instead of claiming a quality score.
- **Retrieval is lexical.** The hashing embedder matches shared words, not meaning. feat-013 measures a small vocabulary-overlapping synthetic baseline, not held-out or real-text quality, and it does not measure abstention (D-008; docs/retrieval-baseline.md).
- **The orchestration benchmark cannot show a quality win** for the specialist roles in mock mode; it shows equal outcomes at higher cost (D-012).

## Security

- **Demo identity, not authentication.** One bearer token stands for one configured user (D-011, D-013). It suits a local or invite-only demo only.
- **Checkpoints store retrieved evidence text.** They are isolated per tenant (D-014), but the spec's goal of storing references instead of text is not met.
- **Tenant isolation assumes typed access.** A session able to run arbitrary SQL as the analytics login could set its own tenant (D-007).
- **Redaction is pattern-based** (D-011).

## Product surface

- No endpoint to list runs, and no approval screen in the UI; approve, resume and fetch exist over HTTP (D-015). Runs live in checkpoints, not rows, so feedback references run ids that are not foreign keys (D-011).
- `POST /v1/runs` in mock mode needs the name of a scripted reply file; it demonstrates the real pipeline, not open-ended tasks (D-013).
- The replay UI is read-only and shows recorded runs only; it has no live mode (D-013).
- Reconciliation of stuck writes runs on demand; nothing schedules it (D-010).
- The workflow writes one kind of action (a sandbox ticket); there are no real external connectors (spec Phase 2).

## Engineering

- `./init.sh` and `npm run setup` from the harness would install into the system Python; sessions use `uv sync` instead (D-004, upstream harness issues #63 and #64).
- The declared verification layers of feat-008 and feat-009 assume PostgreSQL is already running.
- The license (MIT, copied by the harness) is unconfirmed by the owner.
- CI actions are pinned by commit SHA; bumping them is a manual review step.
