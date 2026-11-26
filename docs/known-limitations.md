# Known limitations

What AI AgentOps does not do or has not shown yet, as of feat-013. Each item names the decision record that explains it.

## Evidence and measurement

- **No hosted quality baseline yet.** Tests, replays and the default corpus/benchmark use scripted replies. Two free-tier Gemini 3.5 Flash-Lite runs exist. In the first, the model invented quarters and abstained; after feat-014 (D-017) it plans with real quarters, but most report-writing calls failed on provider overload or network outages, so answer quality is still effectively unmeasured (D-011, D-012, D-016, D-017).
- **Live scoring is outcome-level.** The feat-017 rubric (D-018) checks outcomes, included declines, surviving findings, cited policy documents and safety invariants; it does not grade prose or every required citation. Each case runs once, so differences of a few cases between runs or designs are noise.
- **Free-tier rate limits need pacing.** Without `--min-call-interval`, the fourth live run lost all 12 failing corpus cases to HTTP 429. With a 4-second interval and bounded 429 retries (feat-019) the fifth run had none, but a Retry-After above 60 seconds still fails a case. Once the daily quota runs out, a live run stops early (feat-021) and must be repeated after the reset; detection relies on the provider naming a per-day quota in its 429 message. Multi-source reports sometimes cite only sales data, and a viewer's run may complete from permitted documents rather than abstain; since feat-023 such a run records the denied source as an evidence gap, but whether the summary's wording mentions it is not checked.
- **Policy citation guidance is not measured hosted improvement.** feat-018 asks both
  report paths to cite relevant supporting document passages only when they survive
  context truncation, without inventing policy claims. Offline captured-request tests
  verify the instruction and unchanged citation enforcement, not model compliance or
  entailment. Existing live reports predate this prompt and are retained unchanged.
  The sample mock replay reflects the longer prompt's word-count token estimate,
  not a hosted tokenizer measurement.
- **Provider overload and throttling can still fail a case.** A 503 or connection error gets at most two budget-reserved retries (feat-015); a third failure or a timeout ends the case as failed, and rate limits share the same two retries (feat-019). Each retry reserves about USD 0.32, so long outages exhaust caps faster. Model availability can also change: `gemini-2.5-flash-lite` was withdrawn for new users and replaced (D-016 amendment).
- **Budget reservations are conservative and process-local.** Each call reserves the full input window plus bounded output, with no refund. A small budget may refuse even a short prompt. Prices and token ceilings come from the bundled SDK map, not an invoice or provider-enforced account limit; persistent account-wide budgets remain unimplemented (D-016).
- **Live evaluation is not a replacement quality corpus.** Gateway/reliability scenarios stay mocked, and workflow expectations include scripted errors/trajectories that a real model may not produce. Reports preserve those failures instead of claiming a quality score.
- **Retrieval is lexical.** The hashing embedder matches shared words, not meaning. feat-013 measures a small vocabulary-overlapping synthetic baseline, not held-out or real-text quality, and it does not measure abstention (D-008; docs/retrieval-baseline.md).
- **BM25 is an offline experiment, not an adopted improvement.** feat-020 compares
  one fixed lexical candidate with the vector baseline using already inspected
  synthetic corpora. Neither understands synonyms or negation, and no score threshold
  or abstention behavior is added. Full-catalog Python scoring is not a scalable
  production implementation or a latency measurement.
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
