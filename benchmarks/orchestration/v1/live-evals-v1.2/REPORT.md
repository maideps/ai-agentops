# Orchestration benchmark: single workflow vs. specialists

- Benchmark: orch-bench-v1.0.0
- Dataset: evals-v1.2.0
- Commit: 52b41f88fe92feebf2bc1303d3d8e42a14126ae2
- Mode: live (provider gemini, model gemini/gemini-3.5-flash-lite); hosted-model numbers: recorded below
- Prompt versions: single 24b6ccb937c7, specialists 331f504c5950
- Sample size: 42 workflow cases, each run once per orchestration

| Metric | Single workflow | Specialists |
|---|---|---|
| Live outcome success (feat-016 rubric) | 21/41 | 19/41 |
| Mock-trajectory expectations met | 7/42 | 5/42 |
| Supported findings (citation check) | 100.0% | 100.0% |
| Model calls per run (mean) | 1.62 | 2.19 |
| Tool calls per run (mean) | 1.17 | 1.26 |
| Tokens per run (mean, reported) | 790 | 708 |
| Latency p50 / p95 (ms, local) | 4337 / 9221 | 4679 / 14441 |
| Reported usage cost (USD) | 0.032361 | 0.028296 |

**Recommendation: keep_single_workflow.** Specialists reached 19/41 live outcomes vs 21/41, so they do not measurably win; they cost 2.19 model calls and 708 tokens per run vs 1.62 and 790.

Cases where the orchestrations differ: normal-04 (single pass, specialists fail), normal-09 (single fail, specialists pass), multi-03 (single fail, specialists pass), multi-05 (single fail, specialists pass), missing-03 (single pass, specialists fail), tools-02 (single pass, specialists fail), tools-03 (single pass, specialists fail), tools-05 (single fail, specialists pass), inject-03 (single pass, specialists fail), inject-04 (single pass, specialists fail).

## Limitations

- Live workflow cases run once per orchestration; scripted mock expectations may fail and are not a model-quality rubric.
- Costs use reported tokens at bundled LiteLLM rates, not provider invoices. Reservations include uncertain failed calls and are not refunded.
- Gateway/reliability scenarios are excluded, as in the mock benchmark.
- One shared batch cap covers both orchestrations; budget exhaustion can leave later cases unexecuted, so compare the recorded failures too.
