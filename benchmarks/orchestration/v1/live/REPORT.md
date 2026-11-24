# Orchestration benchmark: single workflow vs. specialists

- Benchmark: orch-bench-v1.0.0
- Dataset: evals-v1.0.0
- Commit: 48355cfe24908866ad048d5a81d976f6493d0171
- Mode: live (provider gemini, model gemini/gemini-3.5-flash-lite); hosted-model numbers: recorded below
- Prompt versions: single 4a2aeafab709, specialists 62ad462853f4
- Sample size: 42 workflow cases, each run once per orchestration

| Metric | Single workflow | Specialists |
|---|---|---|
| Task success (expected outcome reached) | 5/42 | 5/42 |
| Supported findings (citation check) | 100.0% | 100.0% |
| Model calls per run (mean) | 0.98 | 1.62 |
| Tool calls per run (mean) | 0.98 | 1.14 |
| Tokens per run (mean, reported) | 248 | 269 |
| Latency p50 / p95 (ms, local) | 1011 / 2280 | 2091 / 12909 |
| Reported usage cost (USD) | 0.006622 | 0.007381 |

**Recommendation: keep_single_workflow.** Specialists reached 5/42 expected outcomes vs 5/42, so they do not measurably win; they cost 1.62 model calls and 269 tokens per run vs 0.98 and 248.

Cases where the orchestrations differ: access-01 (single pass, specialists fail), budget-01 (single fail, specialists pass).

## Limitations

- Live workflow cases run once per orchestration; scripted mock expectations may fail and are not a model-quality rubric.
- Costs use reported tokens at bundled LiteLLM rates, not provider invoices. Reservations include uncertain failed calls and are not refunded.
- Gateway/reliability scenarios are excluded, as in the mock benchmark.
- One shared batch cap covers both orchestrations; budget exhaustion can leave later cases unexecuted, so compare the recorded failures too.
