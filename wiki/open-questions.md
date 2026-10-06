# Open questions and parked items

Consolidated from the planning discussion. Delete an item when it is decided and recorded in its essay.

## Storytelling

- Grim portents / countdown clocks: explore options before formalizing any mechanism ([01](story/01-what-is-a-story.md)).
- Do cycles represent scales, themes, or a grid? ([02](story/02-structure-and-direction.md))
- Locate the Weis/Hickman nested-cycles essay (Ficus's recollection; not found by web search).
- How individuals within a faction shape the faction's qualities ([03](story/03-character-desire-opposition.md)).
- Reward notice timing for engaging a motivation: immediate vs quiet accrual with recap ([03](story/03-character-desire-opposition.md)).
- Tuning the significance distribution for details player attention anchors ([05](story/05-promises-and-quests.md)).
- Confirm the Proposed quest shape: goal predicate, stakes, status; obstacles live in the world ([05](story/05-promises-and-quests.md)).
- Remaining lenses: interactive-narrative literature, tabletop GM craft, LLM failure modes.

## Architecture

- Difficulty numbers: confirm tier plus difficulty factors, translated by the ruleset ([action pipeline](architecture/action-pipeline.md)).
- Confirm the draft core-element list and the plugin contract hooks ([core engine](architecture/core-engine.md)).
- Time model: confirm the three-way split (commit order, in-world time, causal links), time frames, and which time-travel flavors the engine supports ([time](architecture/time-and-knowledge.md)).
- Server-client: confirm an authoritative server with an in-process server for single player ([multiplayer](architecture/multiplayer-and-api.md)).
- BYOK in a shared world: whose key pays for a world tick?
- Turn structure for parties, and MMO simulation when no players are present.

## Tech

- TerminusDB: in or out, given branching timelines.
- Local-first relational store versus Postgres.
- Gemini context caching behavior for the two-call check turn.
- Model tiering per task, embeddings, evaluation and replay harness.
- Whether a local-model (Ollama) option belongs in the provider abstraction ([tech stack](tech/tech-stack.md)).
