# Tech stack (draft)

*The storytelling discussion deliberately came first; the stack and architecture are built around its findings. Status tags are defined in [../index.md](../index.md).*

## Decided

- **Language:** mainly Python.
- **LLM:** bring-your-own-key (BYOK), initially focused on Gemini as model and provider. Some LLM-interface code may be ported from past projects.
- **Structured output:** likely enforce JSON output from the LLM via a schema.
- **Interfaces:** terminal first, then a terminal UI with the Textual module, and a web interface later. MCP through Claude Desktop and similar tools is an additional option, via an MCP server over the internal API (see [../architecture/multiplayer-and-api.md](../architecture/multiplayer-and-api.md)).
- **Storage intent:** Qdrant for text embeddings and retrieval, plus a relational database such as Postgres for structured state.
- **Per-task models:** different LLM models for different tasks, configurable at the server level.
- **Build order:** 5e first. The engine should support all features of 5e, but systems stay generic (the system-agnostic and free-form goals in [../architecture/core-engine.md](../architecture/core-engine.md) stand). The SRD data lets us start fast by prepopulating things like item and spell lists.
- **Rules data:** vendor the SRD JSON from the database package in `5e-bits/5e-srd-api` and skip its API and MongoDB. Default to the **2024 SRD (SRD 5.2)**, released under CC-BY-4.0, which requires attribution (a `NOTICE` file). The 2014 data is the fallback.
- **5e libraries:** `furlat/dnd_engine` and `codingame-team/dnd-5e-core` are references only, not dependencies.
- **Storage for the prototype:** SQLite with JSON columns behind a thin access layer, with Postgres later for shared worlds. Qdrant is deferred until something needs retrieval.
- **TerminusDB:** parked. Branching and rewindable game states are interesting, but too complicated for now; revisit once other things are built.

## Open, to debate in a dedicated tech-stack discussion

- **Prompt and context caching on Gemini.** Checked against the current docs (see "Verified" below). **[Proposed]** Rely on implicit caching: keep the stable content first in every prompt, make call 2 of a check turn share call 1's prefix, and log cached token counts. Which Gemini API surface to target is still open.
- **Model tiering.** Which tasks go to which models (the check ruling is mostly classification; the narration call needs the strongest model).
- **Embeddings and retrieval.** Deferred with Qdrant. Which embedding model, what is embedded (lore, past narration, summaries, rulings), and how retrieval is combined with the structured store.
- **Strict-causality mode.** It requires a world simulation rich enough to generate drama unaided; how much is deterministic code versus LLM work is a stack question.
- **Evaluation and replay harness.** See [evaluation-and-replay.md](evaluation-and-replay.md).
- **Packaging and configuration.** BYOK key handling (see the open question about whose key pays in a shared world).

## What the repo already contains

*Observed in the repository, not yet discussed, so recorded as facts and not decisions.*

- `local_llm/` holds Ollama runner scripts (`run_ollama_optimized.ps1` and a `.bat`) and `local_llm/tests/sample-rpg-local.py`, a sample text-RPG test script.
- `.gitignore` already excludes Qdrant local storage paths (`.qdrant_storage/`, `storage/`, `.qdrant-initialized`, `snapshots/`) and `.venv/`.

**[Decided]** A local model (Ollama) is a candidate provider alongside Gemini and other API providers. The runner and sample are verified working with a manageable response time. **[Open]** Output quality is untested; see [evaluation and replay](evaluation-and-replay.md). **[Proposed]** The provider abstraction declares per-provider capabilities (schema enforcement, caching, tool calling) and uses validate-and-retry as the common floor. The sample uses Ollama's plain JSON mode (syntax only); whether the installed version accepts a full JSON schema needs verifying.

## Verified against current docs

*Facts checked on the Gemini API documentation in October 2026; they may change.*

- Implicit caching is on by default for Gemini 2.5 and newer models, with savings passed on automatically when a request hits the cache. Minimum input is 4,096 tokens for the Gemini 3.x models listed on the caching page and 2,048 for 2.5. Putting large common content first and sending similar prefixes close together improves hit chances. Hits show in `usage.total_cached_tokens`.
- The newer Interactions API supports implicit caching only; explicit caching needs the older generateContent API. Implicit caching works in stateful and stateless modes.
- Structured output accepts a JSON Schema subset and Pydantic models. Very large or deeply nested schemas may be rejected, and values must still be validated by the application.
