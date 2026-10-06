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

**[Open]** The earlier `[BREAK]` marker in the Ollama sample came from a suggestion that forced-JSON mode strips newlines. The probe found **no paragraph breaks** in a 490-character narration even with a full schema (where an escaped `\n\n` is valid), so the model is not producing them; whether the server suppresses them is not yet separated from the model ignoring the instruction. **[Proposed]** Make paragraphs structural: `"narration"` as a list of paragraph strings with `minItems`, so a break is guaranteed by the schema and the extractor emits a blank line between elements. Being tested by the probe.

**[Proposed]** Changes commit in the background so the player can read and type while they validate. The turn queue is serialised per actor or scene, so the next prompt is always built from committed state. A rejected change triggers a repair call for the changes only, with no re-narration. Check turns commit the check request before the roll.

## Ollama

**[Decided]** Use the HTTP API directly (`httpx`, NDJSON streaming) and not the Python SDK. The SDK's `ChatResponse` (0.6.3) drops `prompt_eval_cached_count`, which Ollama's API docs list and the server logs suggest exists. The field depends on the server version; confirm on a live server.

**[Verified]** Probe run on the author's machine (phi4-mini, October 2026): Ollama accepted a full JSON schema with a nested model and a free-form `dict` field, and the HTTP API reports `prompt_eval_cached_count` (a repeated 1,474-token prompt reported 1,473 cached; the first call reported 19). A CPU-only local model is slow (tens of seconds to minutes per turn), so streaming the narration and committing in the background matter.

**[Open]** Whether Gemini accepts schemas with free-form `dict` fields.

## Prompts

**[Decided]** Prompts are data, not code strings: fragment files (markdown with a few front-matter fields) composed by recipes per situation (free narration, check setup, check outcome, ...), with stable fragments first for caching. Simple `{placeholder}` slots only.

**[Decided]** Variants of a recipe are chosen by a small selection policy (fixed, random per session, or a replay config); each call records recipe, variant and fragment hashes in the event log.

**[Decided]** A second, database layer for per-world overrides comes later behind a fragment-source interface (world overrides first, repo files as fallback). Only the file source is built now.

## A/B runs

**[Proposed]** Run clones of a world (one SQLite file each) concurrently, one per variant. Requirements now: injected config, async providers, and dice that come from the log (seeded or precomputed per turn). Identical player inputs only hold for early turns; later comparison needs a scripted or LLM-driven player, ideally the planned "Claude as player" MCP server.

## Open

- **[Open]** Single-writer scaling. **[Proposed]** Serialise *commits*, not turns (the lock covers only the short commit, not the LLM call); commit with a base-sequence check and repair on conflict; shard by scene. SQLite for now, Postgres for shared worlds.
