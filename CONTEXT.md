# AImaginarium: CONTEXT

Light orientation file. Read this first, then `wiki/index.md`. Detail lives in the wiki essays.

## What this is

An engine for D&D-style tabletop RPGs in which an LLM acts as dungeon master/orchestrator while the **engine owns authoritative state** (inventory, locations, characters, quests, world events) and a **narrative-direction layer** (goals, themes, tropes, setups and payoffs). Single player first; later a party of 2 to 8 and a massively multiplayer shared world.

- Python; bring-your-own-key LLM, Gemini first.
- An internal API shared by every client; MCP servers so tools like Claude Desktop can act as the DM, and separately as a player.
- UI path: terminal, then Textual, then web.

## Status

Early build. Storytelling essays are done, architecture and tech stack are drafted, and the prototype foundations are merged: SRD loader, SQLite world store with event log, and the LLM gateway (providers for Gemini and Ollama, retry, structured output, TOML config). The prompt library and a first playable terminal loop (`python -m aimaginarium`) are in. The repair call, persistent history and the blind model comparison are built. The internal API is in (contract and in-process server in `aimaginarium/api/`, the terminal client runs on it). The trace channel (file sink, dev live stream, `/inspect`) is in. Undo of the last turn (dev role) is in. Next: the Textual UI with dev panels (#66), then the player MCP (#67) (see `wiki/architecture/dev-tools-and-clients.md`); a real director comes later. See `wiki/architecture/action-pipeline.md` ("As built") and `wiki/open-questions.md`.

## Tenets (do not violate)

1. The engine/GM **never makes actions or decisions for the player**. It only says what happens after the player has decided.
2. The player controls what they do, not what the world does. The world moves without them.
3. The engine provides **mechanisms**; the campaign supplies **policy**.
4. The GM always knows more than the player. Players see projections, never hidden state.
5. The LLM adjudicates in the fiction; code rolls dice, validates and commits.
6. No lists of options, outcomes or consequences are shown to the player.

## Wiki conventions

Statements are tagged **[Decided]** (Ficus stated or accepted), **[Proposed]** (Claude proposed, discussed, not explicitly confirmed) or **[Open]**. Do not promote a Proposed item to Decided without confirmation.

## Layout

- `wiki/story/`: storytelling essays
- `wiki/architecture/`: core engine, action pipeline, time and knowledge, multiplayer and API
- `wiki/tech/`: tech stack
- `aimaginarium/`: the engine package (`srd/`, `world/`, `llm/`, `api/`); clients in `ui/` (`cli/`, `tui/`)
- `tests/`: the automated test suite
- `local_llm/`: Ollama runner scripts and sample scripts (`sample/`), not part of the suite

## Working agreement

Issue, fix, commit, PR, merge: every change gets a GitHub issue with at least one label (`bug`, `feature` for now), and the commit/PR closes it. Prefer sandbox clones and targeted reads over passing whole files through MCP. A fine-grained token is provided at the start of each session and is never stored.
