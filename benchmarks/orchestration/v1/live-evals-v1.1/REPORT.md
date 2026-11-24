# Orchestration benchmark: single workflow vs. specialists

- Benchmark: orch-bench-v1.0.0
- Dataset: evals-v1.1.0
- Commit: a167ca3d43433942a80ca44963b1270117e24025
- Mode: live (provider gemini, model gemini/gemini-3.5-flash-lite); hosted-model numbers: recorded below
- Prompt versions: single 24b6ccb937c7, specialists 331f504c5950
- Sample size: 42 workflow cases, each run once per orchestration

| Metric | Single workflow | Specialists |
|---|---|---|
| Task success (expected outcome reached) | 4/42 | 2/42 |
| Supported findings (citation check) | 100.0% | 100.0% |
| Model calls per run (mean) | 1.45 | 2.05 |
| Tool calls per run (mean) | 0.81 | 1.05 |
| Tokens per run (mean, reported) | 384 | 407 |
| Latency p50 / p95 (ms, local) | 1246 / 10910 | 2176 / 11117 |
| Reported usage cost (USD) | 0.013844 | 0.017037 |

**Recommendation: keep_single_workflow.** Specialists reached 2/42 expected outcomes vs 4/42, so they do not measurably win; they cost 2.05 model calls and 407 tokens per run vs 1.45 and 384.

Cases where the orchestrations differ: normal-03 (single pass, specialists fail), normal-06 (single pass, specialists fail).

## Limitations

- Live workflow cases run once per orchestration; scripted mock expectations may fail and are not a model-quality rubric.
- Costs use reported tokens at bundled LiteLLM rates, not provider invoices. Reservations include uncertain failed calls and are not refunded.
- Gateway/reliability scenarios are excluded, as in the mock benchmark.
- One shared batch cap covers both orchestrations; budget exhaustion can leave later cases unexecuted, so compare the recorded failures too.
