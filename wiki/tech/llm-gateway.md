# LLM gateway

*Design for issue #15 (provider interface). Status tags are defined in [../index.md](../index.md). Settled in discussion in October 2026.*

## Layering

**[Decided]** Clients (terminal, Textual, web, MCP) call the internal API, which calls the engine; the engine alone uses the world store, ruleset, prompt library and LLM gateway. Clients never see a provider; `LLMProvider` is internal to the server.

**[Decided]** For the terminal prototype (#16) there is no API layer yet, only a small in-process facade (for example `Game.take_turn(actor, text)`). It must be commented as **temporary**; it is the boundary the API and MCP wrappers will later expose.

## Package layout

**[Decided]** A generic `LLMProvider` as the middleman, with one module per provider, so many more can be added later.

```
aimaginarium/llm/
  base.py        Request, Response, Usage, Capabilities, LLMProvider
  retry.py       backoff helper
  structured.py  validate-and-retry around any provider
  factory.py     provider from config, per-task model choice (planned)
  providers/     gemini.py, ollama.py, fake.py, ...
```

Dependencies point one way: `llm/` knows nothing about the game, `prompts/` builds text and never calls a provider, `engine/` uses both.

## Provider interface

- **[Decided]** Async-first (concurrent runs, background commits, Textual, web and MCP all lean async), with a sync wrapper for the terminal.
- **[Decided]** Stateless calls; the engine owns state. No module-level singletons or global config, so several engines can run in one process (needed for A/B runs).
- **[Decided]** Capabilities are declared **per model**, not per provider (users bring their own models, including larger ones the author cannot run). Defaults ship with the project and users can override them.
- **[Decided]** Validate-and-retry is the common floor; `StructuredCaller` feeds the validation errors back to the model.
- **[Proposed]** `stream()` yields `Chunk` items then one `Response`; `generate()` drains it. Usage carries `cached_tokens`, `None` when the provider cannot report it.

## Reply shape

**[Decided]** One call per turn returns **one JSON object** with the narration as its first field: `{"narration": ..., "check": ..., "changes": [...]}`. Provider schema or JSON modes constrain the whole reply to JSON, so prose followed by JSON cannot be enforced. The narration streams to the player while the rest is still being generated.

**[Proposed]** A small incremental extractor pulls the narration string out of the streaming JSON and unescapes it. Paragraphs are `\n\n` escapes.

**[Proposed]** Function calling (text part plus a schema-checked call) is a later optimisation for models that handle it well; the engine does not need to know which strategy a provider used. Property order matters for streaming (Gemini has a property-ordering setting; to verify).

**[Open]** The earlier `[BREAK]` marker in the Ollama sample came from a suggestion that forced-JSON mode strips newlines. The probe found **no paragraph breaks** in a 490-character narration even with a full schema (where an escaped `\n\n` is valid), so the model is not producing them; whether the server suppresses them is not yet separated from the model ignoring the instruction. **[Verified]** With `"narration"` as a list of strings with a minimum of two items, the same model returned separate paragraphs (the single-string form still returned none).

**[Proposed]** **Narration plan:** paragraphs are discrete units. A recipe declares an ordered list of paragraph slots (id, instruction, count), for example an opening turn with world overview (3), place (2) and scene (2, drawing on the character sheet). The schema is built from the plan, so counts are enforced by structure; the slot instructions are rendered into the prompt; and the extractor streams each paragraph tagged with its slot. This lets recipes shape story structure, and later allows per-paragraph pacing, storage, regeneration and A/B variants.

**[Proposed]** Changes commit in the background so the player can read and type while they validate. The turn queue is serialised per actor or scene, so the next prompt is always built from committed state. A rejected change triggers a repair call for the changes only, with no re-narration. Check turns commit the check request before the roll.

## Ollama

**[Decided]** Use the HTTP API directly (`httpx`, NDJSON streaming) and not the Python SDK. The SDK's `ChatResponse` (0.6.3) drops `prompt_eval_cached_count`, which Ollama's API docs list and the server logs suggest exists. The field depends on the server version; confirm on a live server.

**[Verified]** Probe run on the author's machine (phi4-mini, October 2026): Ollama accepted a full JSON schema with a nested model and a free-form `dict` field, and the HTTP API reports `prompt_eval_cached_count` (a repeated 1,474-token prompt reported 1,473 cached; the first call reported 19). A second run reproduced all three results. A CPU-only local model is slow (tens of seconds to minutes per turn), so streaming the narration and committing in the background matter.

**[Open]** Whether Gemini accepts schemas with free-form `dict` fields.

## Gemini

**[Decided]** Use Google's official `google-genai` SDK (an optional extra, `aimaginarium[gemini]`), behind `LLMProvider`, so it can be replaced without touching the engine. Unlike the Ollama SDK, it is the first-party reference client; it exposes async streaming, `cached_content_token_count`, thinking tokens and full JSON schemas (`response_json_schema`). Thinking tokens are counted as output tokens in `Usage`. Extra generation config (for example a thinking budget) is passed through the provider's `config` dict.

**[Verified]** Probe run with `gemini-3.5-flash-lite` (October 2026): the full schema with a nested model and a free-form `dict` was accepted; the narration key came first in the reply; a single string narration produced escaped `\n\n` paragraph breaks (the paragraph problem is specific to small local models), and the list form returned three paragraphs.

**[Open]** Prompt cache: 0 cached tokens on a repeated 1,473-token prefix. Google's caching docs (updated August 2026) give a 4,096-token minimum for the Gemini 3.5 series and do not list flash-lite, so this was probably below the minimum. Retest with a prefix above 4,096 tokens (`probe_llm.py gemini <model> 500`). Implicit caching is best-effort, so a hit is not guaranteed.

**[Verified]** `Usage.time_to_first_token` is measured by every provider through `ResponseTimer`, so clients and tests read it the same way. `tests/test_gemini_models.py` (needs a key; skipped without one) checks status, TTFT and total time for `gemini-3.5-flash-lite` and two Gemma models, which the free tier offers at 14,400 requests per day each. `gemma-4-31b-it` often answers 500 or 503. **[Open]** Whether the Gemma models handle schema-constrained JSON and a system prompt well enough for the cheaper tasks (such as the check ruling); only liveness and timing are tested so far.

**[Decided]** The provider switches off the SDK's automatic function-calling loop (the engine executes tool calls, not the SDK).

## Retries and outages

**[Decided]** Busy responses (Gemini 503 and 429, timeouts, connection errors) are common, so every provider the factory builds is wrapped in `RetryingProvider`. A call is retried with exponential backoff and jitter only if it failed before any text reached the caller. When the server states how long to wait (Gemini's `RetryInfo`), that wait is used.

**[Proposed]** `RetryPolicy` defaults: 6 attempts, 1 s doubling to at most 20 s per wait, 45 s in total. Past those limits, or if the server asks for more than the per-wait limit, the wrapper raises `ProviderUnavailableError` (with the attempts and time waited) and does not wait further. A client can show progress through the `on_retry` callback. The `retry` config key overrides the policy globally or per provider.

**[Proposed]** Nothing has been committed to the world when a call fails, because changes commit only after a validated reply, so giving up is safe. What to do next is the engine's decision, in this order of preference: (1) fall back to the next provider or model configured for the task (for example flash-lite, then flash, then a local model); (2) keep the player's action pending, tell them the storyteller is busy, and offer to retry; (3) for background work such as world ticks, requeue with a longer window.

**[Open]** A free-tier daily quota error is a 429 that backoff cannot fix. It is handled only if the server's suggested wait exceeds the per-wait limit; whether Gemini sends one for daily quotas is unverified. A failure after narration has started streaming is not retried; the engine decides (for example a repair call for the changes only).

## Configuration

**[Proposed]** `ProviderFactory` takes a plain mapping: named `providers` (kind, default model, kind-specific settings such as `options` or `config`, optional per-model `capabilities`) and `tasks` (task name to provider and optional model, with a `default` task). `factory.route("narrate")` returns the provider and model for a task, so different tasks can use different models (a small model for the check ruling, the strongest for narration). API keys are never in the mapping: each provider names the environment variable that holds its key (default `GEMINI_API_KEY`), loaded from `.env`, which is git-ignored. **[Decided]** The mapping is read from a TOML file (`aimaginarium.toml`, git-ignored; `aimaginarium.example.toml` is the template). The path comes from an argument, then `AIMAGINARIUM_CONFIG`, then the current directory; `factory_from_file()` builds the factory from it.

## Prompt layout and cost (measured)

**[Verified]** Local timings (phi4-mini, CPU, October 2026): time to first token grew linearly with input size at about 0.1 s per prompt token in every run (40 s at 339 tokens, 158 s at 1,472), so the prompt was being re-evaluated almost in full each turn. The sample script put the changing world state inside the system prompt; any change there invalidates the cache from that point on (its logs showed only 129 and 159 tokens reused). Rule: **stable content first; volatile state last** (in the final user message, after history).

**[Verified]** Generation slowed as context grew (about 2.1 to 1.4 words per second from turn 1 to 5), so prompt size matters beyond caching. A 32,768-token context cost about 4x the model load time (142 s vs 33 s) but no per-turn time at these sizes; `q8_0` KV cache gave no speed benefit at 2,048 tokens (with flash attention confirmed on, prefill looked 20 to 40 percent slower in single runs). Long-context behaviour is untested.

**[Decided]** Ollama options (`num_ctx`, `num_thread`, ...) are passed through the provider's `options` dict.

## Prompts

**[Decided]** Prompts are data, not code strings: fragment files (markdown with a few front-matter fields) composed by recipes per situation (free narration, check setup, check outcome, ...), with stable fragments first for caching. Simple `{placeholder}` slots only.

**[Decided]** Variants of a recipe are chosen by a small selection policy (fixed, random per session, or a replay config); each call records recipe, variant and fragment hashes in the event log.

**[Decided]** A second, database layer for per-world overrides comes later behind a fragment-source interface (world overrides first, repo files as fallback). Only the file source is built now.

## A/B runs

**[Proposed]** Run clones of a world (one SQLite file each) concurrently, one per variant. Requirements now: injected config, async providers, and dice that come from the log (seeded or precomputed per turn). Identical player inputs only hold for early turns; later comparison needs a scripted or LLM-driven player, ideally the planned "Claude as player" MCP server.

## Open

- **[Open]** Single-writer scaling. **[Proposed]** Serialise *commits*, not turns (the lock covers only the short commit, not the LLM call); commit with a base-sequence check and repair on conflict; shard by scene. SQLite for now, Postgres for shared worlds.
