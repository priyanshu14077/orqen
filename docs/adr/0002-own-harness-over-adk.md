# ADR 0002: Our own agent loop with model adapters, Claude first

**Status:** accepted · 2026-11-09 · supersedes the Gemini + Google ADK plan

## Context

Prompt-spec submissions need an agent loop that the platform owns. Code submissions
need an `llm` client to call. Both run inside the sandbox, and every model call must
be metered and limited.

## Decision

- `orqen_harness` implements the loop: call the model, run tool calls, repeat until a
  final answer or `max_steps`.
- The loop depends only on the `ModelAdapter` protocol
  (`complete(messages, tools, params) -> Turn`). Claude is the first adapter.
- The LLM proxy speaks the Anthropic Messages API format. In the sandbox,
  `ANTHROPIC_API_KEY` is a per-run token and `ANTHROPIC_BASE_URL` points at the proxy;
  the real key exists only in the proxy.
- The LLM judge reuses the same adapter in a single-call, structured-output mode.
- `orqen_harness` has no server-side dependencies, so it can be installed in the
  sandbox image on its own.

## Why not ADK

ADK's runner, sessions and evaluator are built for one developer's agent. We need the
loop to be small, auditable and provider-neutral, and we need metering at the proxy
rather than in callbacks that user code in the same process can monkeypatch.

## Consequences

Everything inside the sandbox, including our harness, is untrusted. Budgets, the model
allowlist, temperature limits and the tool-call trace are enforced and recorded in the
proxy. Adding a provider means adding an adapter and a proxy translation.
