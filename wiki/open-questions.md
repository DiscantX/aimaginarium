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
- Remaining lens: tabletop GM craft.
- Recovery when permadeath is off: whether the engine requires recovery to cite an existing world fact, and the range of defeat outcomes; tune in testing ([04](story/04-agency-and-tenets.md#failure-and-recovery)).
- How the engine frames a session boundary: goal resolved, next goal open ([05](story/05-promises-and-quests.md#session-boundaries)).
- Tension for a tension-curve director: computed, LLM-estimated, or both; which director is the second implementation; whether a human-DM-assisted mode is in scope ([07](story/07-interactive-narrative.md)).
- Local model output quality for each task, pending the evaluation suite ([06](story/06-llm-failure-modes.md)).

## Architecture

- Where the tier and factors are decided: in call 1 (today) or in a separate focused call before the roll ([action pipeline](architecture/action-pipeline.md)).
- Confirm the draft core-element list and the plugin contract hooks ([core engine](architecture/core-engine.md)).
- Time model: confirm the three-way split (commit order, in-world time, causal links), time frames, and which time-travel flavors the engine supports ([time](architecture/time-and-knowledge.md)).
- Server-client: confirm an authoritative server with an in-process server for single player ([multiplayer](architecture/multiplayer-and-api.md)).
- BYOK in a shared world: whose key pays for a world tick?
- MMO simulation when no players are present. Party turn handling is deferred ([multiplayer](architecture/multiplayer-and-api.md)).
- Table settings: which are injected into prompts and which enforced in code ([core engine](architecture/core-engine.md)).

## Tech

- TerminusDB: in or out, given branching timelines.
- Local-first relational store versus Postgres.
- Gemini context caching behavior for the two-call check turn.
- Model tiering per task, embeddings, evaluation and replay harness.
- Evaluation and replay: who judges judged checks, where scenarios live, which metrics gate changes ([evaluation](tech/evaluation-and-replay.md)).
- Provider abstraction must declare per-provider capabilities (schema enforcement, caching, tool calling); verify whether the installed Ollama accepts a full JSON schema ([tech stack](tech/tech-stack.md)).
