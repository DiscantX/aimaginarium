# Tech stack (draft)

*The storytelling discussion deliberately came first; the stack and architecture are built around its findings. Status tags are defined in [../index.md](../index.md).*

## Decided

- **Language:** mainly Python.
- **LLM:** bring-your-own-key (BYOK), initially focused on Gemini as model and provider. Some LLM-interface code may be ported from past projects.
- **Structured output:** likely enforce JSON output from the LLM via a schema.
- **Interfaces:** terminal first, then a terminal UI with the Textual module, and a web interface later. MCP through Claude Desktop and similar tools is an additional option, via an MCP server over the internal API (see [../architecture/multiplayer-and-api.md](../architecture/multiplayer-and-api.md)).
- **Storage intent:** Qdrant for text embeddings and retrieval, plus a relational database such as Postgres for structured state.
- **Per-task models:** different LLM models for different tasks, configurable at the server level.

## Open, to debate in a dedicated tech-stack discussion

- **TerminusDB.** Used in the HumanTechTree project. Ficus does not think version control is needed here, so it is probably out. One scenario would argue for it: **branching timelines** under time travel (see [../architecture/time-and-knowledge.md](../architecture/time-and-knowledge.md)). Worth settling whether that case is in scope.
- **Local-first story for the relational store.** **[Proposed flag]** A single-player terminal game requiring a Postgres server is heavy. Consider whether a lightweight embedded database for local play and Postgres for shared worlds can share one schema and access layer. Qdrant already has a local mode (see below).
- **Prompt and context caching on Gemini.** The two-call check turn relies on call 2 reusing call 1's context cheaply. Verify current provider behavior before depending on it.
- **Model tiering.** Which tasks go to which models (the check ruling is mostly classification; the narration call needs the strongest model).
- **Embeddings.** Which embedding model, what is embedded (lore, past narration, summaries, rulings), and how retrieval is combined with the structured store.
- **Strict-causality mode.** It requires a world simulation rich enough to generate drama unaided; how much is deterministic code versus LLM work is a stack question.
- **Evaluation and replay harness.** Replaying logged scenarios under different directors, and measuring tier/outcome distributions, needs tooling decisions early.
- **Packaging and configuration.** BYOK key handling (see the open question about whose key pays in a shared world).

## What the repo already contains

*Observed in the repository, not yet discussed, so recorded as facts and not decisions.*

- `local_llm/` holds Ollama runner scripts (`run_ollama_optimized.ps1` and a `.bat`) and `local_llm/tests/sample-rpg-local.py`, a sample text-RPG test script.
- `.gitignore` already excludes Qdrant local storage paths (`.qdrant_storage/`, `storage/`, `.qdrant-initialized`, `snapshots/`) and `.venv/`.

**[Open]** Whether a local-model option (Ollama) belongs in the provider abstraction alongside Gemini, since the scripts suggest local models have been tried.
