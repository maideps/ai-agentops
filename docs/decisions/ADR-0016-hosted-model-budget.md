# ADR-0016: Hosted-model cost reservations

- Date: 2026-11-24
- Status: accepted
- Requirements: FR-009, FR-010, NFR-009; feature: feat-012

## Context

The owner chose Gemini Flash-Lite as the first hosted model and approved conservative
pre-call reservation, not an estimated cap that can overspend. Input contains message,
tool and schema overhead; whitespace counts cannot bound provider tokens. Concurrent
dispatch, cancellation and timeouts also make post-response accounting insufficient.

## Decision

The deny-by-default registry exposes `gemini/gemini-2.5-flash-lite` for tool calling,
structured output and usage reporting. The adapter does not expose streaming.
Trusted configuration reads `GEMINI_API_KEY`; a key never selects a mode. HTTP live runs
need the existing mode and enable flags; their USD budget defaults to zero.

Before each budgeted dispatch, atomically reserve the registered full input window
(1,048,576 tokens) plus `max_output_tokens`, at the bundled LiteLLM text rates
(USD 0.0000001/input token, USD 0.0000004/output token). This includes unknown tool/schema
overhead without introducing a tokenizer network request. Use decimal arithmetic for
accumulation. Never refund a reservation, even after success or cancellation; no SDK
retries. Missing/invalid prices prevent dispatch. Missing or out-of-bound usage is an
explicit error and cannot release a reservation.

The opt-in evaluation CLI shares one total cap over the command and still caps each run.
Mock remains default regardless of live environment flags; replay recording stays mock-only.
Live reports separate returned-token cost from reserved cost and retain failed cases.
Gateway/reliability scenarios remain mocked; scripted workflow expectations are not a
real-model quality rubric. Manual live evidence requires separate owner approval.

## Alternatives

- Estimate words or tokenize messages only: rejected; neither includes a defensible
  upper bound on all provider-side overhead.
- Refund after errors: rejected; a lost response may follow a billed completion.
- Reserve only after responses: rejected; concurrent requests can overspend first.
- Add a persistent billing service now: deferred; larger than this first hosted-call slice.

## Consequences and assumptions

Short prompts can be refused by small budgets. Every 500-output-token call reserves
USD 0.1050576 even when reported usage costs much less. A failed call's invoice cost
can be unknown; retained reservations are not evidence of actual spend.

The bound assumes the provider honors its registered input/output ceilings, the bundled
text prices, and one completion per dispatch. It is not a provider-enforced account cap,
an invoice guarantee, or a persistent multi-process budget. API resume makes no model
calls; evaluation restarts constitute a new manually approved batch.

## Reversal

Replace this approach when a provider-enforced/persistent budget or a verified whole-request
token counter supplies an equally defensible bound. Keep fail-closed dispatch, explicit
opt-in, uncertain-call accounting, and offline CI.
