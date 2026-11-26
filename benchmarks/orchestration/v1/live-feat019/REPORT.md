# Orchestration benchmark: single workflow vs. specialists

- Benchmark: orch-bench-v1.0.0
- Dataset: evals-v1.2.0
- Commit: 92ac088645c3c8a3a09c6fba53a4236cd5ae77a3
- Mode: live (provider gemini, model gemini/gemini-3.5-flash-lite); hosted-model numbers: recorded below
- Prompt versions: single 24b6ccb937c7, specialists 331f504c5950
- Sample size: 42 workflow cases, each run once per orchestration

| Metric | Single workflow | Specialists |
|---|---|---|
| Live outcome success (D-018 rubric) | 37/41 | 38/41 |
| Mock-trajectory expectations met | 7/42 | 5/42 |
| Supported findings (citation check) | 100.0% | 100.0% |
| Model calls per run (mean) | 1.86 | 2.79 |
| Tool calls per run (mean) | 1.64 | 1.86 |
| Tokens per run (mean, reported) | 1296 | 1311 |
| Latency p50 / p95 (ms, local) | 8610 / 12379 | 13976 / 21966 |
| Reported usage cost (USD) | 0.057554 | 0.056607 |

**Recommendation: adopt_specialists.** Specialists reached 38/41 live outcomes vs 37/41 for the single workflow.

Cases where the orchestrations differ: normal-04 (single pass, specialists fail), normal-05 (single pass, specialists fail), multi-04 (single fail, specialists pass), multi-07 (single fail, specialists pass), multi-08 (single fail, specialists pass).

## Limitations

- Live workflow cases run once per orchestration; scripted mock expectations may fail and are not a model-quality rubric.
- Costs use reported tokens at bundled LiteLLM rates, not provider invoices. Reservations include uncertain failed calls and are not refunded.
- Gateway/reliability scenarios are excluded, as in the mock benchmark.
- One shared batch cap covers both orchestrations; budget exhaustion can leave later cases unexecuted, so compare the recorded failures too.
