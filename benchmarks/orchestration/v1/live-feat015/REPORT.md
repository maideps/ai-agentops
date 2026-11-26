# Orchestration benchmark: single workflow vs. specialists

- Benchmark: orch-bench-v1.0.0
- Dataset: evals-v1.1.0
- Commit: 41ea7f0fac53cfb8894dbcb26212823a565dff91
- Mode: live (provider gemini, model gemini/gemini-3.5-flash-lite); hosted-model numbers: recorded below
- Prompt versions: single 24b6ccb937c7, specialists 331f504c5950
- Sample size: 42 workflow cases, each run once per orchestration

| Metric | Single workflow | Specialists |
|---|---|---|
| Task success (expected outcome reached) | 2/42 | 4/42 |
| Supported findings (citation check) | 100.0% | 100.0% |
| Model calls per run (mean) | 1.57 | 1.88 |
| Tool calls per run (mean) | 1.07 | 0.91 |
| Tokens per run (mean, reported) | 554 | 503 |
| Latency p50 / p95 (ms, local) | 2760 / 30880 | 3352 / 31615 |
| Reported usage cost (USD) | 0.021048 | 0.020278 |

**Recommendation: adopt_specialists.** Specialists reached 4/42 expected outcomes vs 2/42 for the single workflow.

Cases where the orchestrations differ: normal-03 (single fail, specialists pass), normal-05 (single fail, specialists pass).

## Limitations

- Live workflow cases run once per orchestration; scripted mock expectations may fail and are not a model-quality rubric.
- Costs use reported tokens at bundled LiteLLM rates, not provider invoices. Reservations include uncertain failed calls and are not refunded.
- Gateway/reliability scenarios are excluded, as in the mock benchmark.
- One shared batch cap covers both orchestrations; budget exhaustion can leave later cases unexecuted, so compare the recorded failures too.
