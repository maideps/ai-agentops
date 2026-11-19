# Orchestration benchmark: single workflow vs. specialists

- Benchmark: orch-bench-v1.0.0
- Dataset: evals-v1.0.0
- Commit: 3adeb9f9bf381ed3468b44753c7cc7dad7d7f138
- Mode: mock (provider mock, model mock-deterministic-v1); hosted-model numbers: none
- Prompt versions: single 4a2aeafab709, specialists 62ad462853f4
- Sample size: 42 workflow cases, each run once per orchestration

| Metric | Single workflow | Specialists |
|---|---|---|
| Task success (expected outcome reached) | 42/42 | 42/42 |
| Supported findings (citation check) | 89.1% | 89.1% |
| Model calls per run (mean) | 1.81 | 2.74 |
| Tool calls per run (mean) | 1.57 | 1.55 |
| Tokens per run (mean, estimate) | 191 | 230 |
| Latency p50 / p95 (ms, local) | 159 / 208 | 172 / 238 |
| Cost (USD) | 0.00 | 0.00 |

**Recommendation: keep_single_workflow.** Specialists reached 42/42 expected outcomes vs 42/42, so they do not measurably win; they cost 2.74 model calls and 230 tokens per run vs 1.81 and 191.

Cases where the orchestrations differ: none.

## Limitations

- Mock mode: model replies are scripted per case, so answer quality is not compared; task success measures whether the platform reaches each case's expected outcome.
- Specialist scripts are derived mechanically from the baseline scripts (document calls to the research role, sales calls to the analyst role), so both see the same model intent.
- Tokens are a deterministic word-count estimate from the mock provider, not a tokenizer.
- Latency is local wall time including PostgreSQL; it varies between machines and runs.
- Cost is 0 in mock mode; no hosted model was called.
- Reliability and gateway-only scenarios are orchestration-independent and are excluded; the sample is the corpus's workflow cases.
