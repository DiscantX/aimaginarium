# Dev tools and clients

*Design note. Status tags are defined in [../index.md](../index.md). Builds on [multiplayer-and-api.md](multiplayer-and-api.md); the highlighting design has its own note, [entity-highlighting.md](entity-highlighting.md).*

## Goals and build order

**[Decided]** Two near-term goals, both to speed up troubleshooting and live testing of the engine: (a) a Textual interface with dev panels, and (b) an LLM-as-player MCP server so Claude can play the game and test it.

**[Decided]** Both are clients of the internal API (contract in #56, in-process server and terminal client in #57). Build order: **1. internal API, 2. Textual UI, 3. player MCP.**

**[Decided]** Dev tools need not ship in production, or ship disabled.

**[Decided]** Principle: anything the AI does behind the scenes must be inspectable in dev. The minimum for the Textual UI is a panel to inspect state and a panel for technical and server logs.

## The internal API

**[Decided]** One API with two roles, `player` and `dev`. The dev role is enabled by server config and refused when disabled (production). One surface avoids two code paths drifting apart.

**[Decided]** The player role returns projections only, never hidden state (tenet 4; see [time-and-knowledge.md](time-and-knowledge.md)). The player MCP server is the natural test of that.

**[Decided]** Slash commands and the command palette are for **system and out-of-character commands only**. In-game actions are always described by the player as prose input. So the API has two input paths: player input (plain text handed to the narrator) and system commands (layout, undo, snapshot, quit, and so on). The palette needs to know only system and dev actions, never in-game verbs.

**[Proposed]** Commands in, events out. Clients send commands and subscribe to an event stream; panels and MCP tools render the same data. The terminal prototype's turn stream (`Narration`, `CheckCalled`, `Committed`, ...) is the seed of the stream.

**[Proposed]** A **trace channel**, separate from both the game event stream and the event log, carries what the engine and LLM do behind the scenes, as structured events with a file sink and a live stream. It is the dev role's subscription. Contents:

- every LLM call: task, provider and model, fallback hops and cool-downs, retries and backoff, time to first token, latency, token counts and cache hits;
- the full prompt as assembled (recipe, fragments, variant) and the raw reply before parsing;
- validation: proposed changes, accepted or rejected, repair call and reasons;
- check workings: tier, factors, difficulty, roll, total;
- state diffs per turn, taken from the event log;
- highlight mentions that were dropped or flagged (see [entity-highlighting.md](entity-highlighting.md)).

This replaces the dev-tools item previously in [../open-questions.md](../open-questions.md).

### The contract (built in #56, `aimaginarium/api/`)

**[Decided]** A check pauses the turn through **one path only**: an explicit `Roll` command. `send(SubmitAction)` streams the turn up to `CheckCalled` and ends with `Done(awaiting_roll=True)`; `send(Roll)` continues it with `RollResult`, the outcome narration and the commit. Built in #57: the engine's turn ends at `CheckCalled` and `Game.resolve_check()` continues it, so remote and in-process clients behave alike.

**[Proposed]** The rest of the shape:

- **Commands.** Player path: `OpenScene`, `SubmitAction(text)`, `Roll`. System path: `GetPlayerView`, `Quit`, and dev-only `Undo`, `GetState(perspective)`, `GetTrace(since, limit)`. There are no in-game verbs.
- **Events.** Every reply stream ends with `Done`. The terminal's turn events carry over (`Narration`, `CheckCalled`, `Repairing`, `ChangesRejected`, `ReplyUnreadable`); `Committed` becomes `StateChanged`, and `RollResult`, `CommandRejected`, `StateView`, `TurnRetracted` and the dev-only `TraceEvent` are new. Each is wrapped in an `Envelope` with a sequence number and turn id.
- **Roles are enforced in one place.** Each event class lists the roles that may see it, and fields only the dev role may see are marked `dev_only`; `for_role` strips them. Dev-only today: the GM's `reason` and the difficulty workings on `CheckCalled`, the raw errors on `ChangesRejected`, the raw changes on `StateChanged`, and the GM state view.
- **Protocols.** `Server.connect(role)` returns a `Session` with `send`, `subscribe` and `close`. Asking for the dev role while config disables it raises `RoleError`.

## Undo, replay and snapshots

**[Decided]** Build **undo** (take back the last turn) and make it available in dev, so Ficus can judge how it affects play. Whether players ever get it is **[Open]**: it touches the stance that the player never truly loses, and players could use it to claw back results they dislike. One option to weigh later is limiting it to input mistakes.

**[Decided]** A retracted turn is shown **greyed out** in dev panels, with its original role styling underneath.

**[Decided]** The event log stays append-only, and the model must never see stale information.

**[Proposed]** Mechanism. Undo appends a `turn.retracted` event naming the turn. State is then rebuilt by replaying the **effective log**: every event except those of retracted turns. This needs no inverse events because `apply_event` is the only code that writes state and reads only the event payload. Only a suffix of turns can be undone (the latest turn, then the one before it), never one in the middle, because later turns may depend on it. Details:

- One **effective view** of the log serves history loading (`Game._load_history` currently reads every `llm.call`), prompt building, the precedent log, projections and `verify_replay`. A single choke point means no path can forget to exclude a retracted turn.
- Entity ids are not reused after an undo, so ids in the trace stay unambiguous.
- A retried turn reuses the recorded roll, so undo cannot be used to reroll.
- Full replay is fine at prototype scale; checkpoints can come later.

**[Proposed]** **Dry-run replay** never touches the live world. It copies the pre-turn state into a scratch database and re-runs the turn with a different model, prompt variant or edited prompt, then shows a diff. It is the same mechanism as the cloned databases in the A/B idea (see [../tech/evaluation-and-replay.md](../tech/evaluation-and-replay.md)), so it is built once.

**[Proposed]** **Snapshot and restore** of the world database for coarse rollbacks in dev.

**[Proposed]** Input guard: the Textual input intercepts large or multi-line pastes and asks before sending. This was prompted by pasting code into the input by accident, which needs no rollback at all.

## Panels and layouts

**[Decided]** The Textual UI uses the `textual-widgets` package (splitters for mouse-resizable panels) from the start. Textual has no built-in docking system; core provides layout primitives and CSS show and hide.

**[Decided]** Player-facing gameplay panels (player stats, inventory, spell lists, possible quests, and similar information common in RPGs) are designed to be shared by the Textual and web UIs, separate from dev panels.

**[Proposed]** Each panel is a self-contained view over an API query or event subscription, with an id, a role (`player` or `dev`) and a default slot. The data contract lives in the API, so Textual and web differ only in the renderer, and player panels automatically receive projections. Dev panels register only when the dev role is enabled.

**[Proposed]** Layouts are named presets in config (for example `play`, `debug`, `ab-compare`), switched by keybinding or the command palette.

**[Proposed]** Dev panels:

- call timeline: one row per call, expandable to prompt, reply and timings;
- state inspector: entity tree with `established` facts, with a toggle between the GM view and the player's projection;
- per-turn world diffs;
- check workings;
- log pane, filterable by level and component;
- routing and config view (which model each task is using, retry and fallback status, cool-downs);
- the live auto-updating panel showing what `/state` shows now.

**[Decided]** A/B testing may need several main chat panels showing prompts and replies, each possibly with its own input box, in IDE-like or game-engine-like layouts that are only for dev. **[Proposed]** Each pane is bound to its own cloned world database and variant, with a "sync input" toggle that sends one input to all panes.

## Dev controls

**[Proposed]** Dev-role actions, all logged as dev events so they do not pollute the narrative:

- dry-run replay, undo, snapshot and restore (above);
- edit state directly (give an item, move the player, set a fact);
- force a dice result or difficulty, to test natural 1 and 20 prompts on demand;
- pause before commit and approve or reject the proposed changes;
- a token and call budget counter, useful on free tiers.

## MCP servers

**[Decided]** MCP dev tools are unavailable by default and enabled through config. **[Proposed]** The server registers them conditionally at startup, so a client never sees them otherwise. The protocol also has a list-changed notification, but Claude Desktop may only re-read tools on restart, so plan on restarting. Hiding is a convenience; the API enforces roles itself.

**[Proposed]** Player MCP tools:

- player role: `submit_action`, `roll` (reveals the precomputed roll), `get_player_view` (projection only);
- dev role, registered only when enabled: `get_trace`, `get_state` (GM view), `get_last_prompt`, `set_state`, `force_roll`, `snapshot` and `restore`, `new_game` (demo world or seed);
- test harness: a scripted scenario runner that returns a pass or fail report, plus adversarial play (probing the yes-machine failure, ignoring quests, trying to get the narrator to decide for the player).

**[Proposed]** DM MCP (Claude acts as the dungeon master; not built soon, but designed for now to avoid retrofitting). The DM chat and the player chat may be one conversation or separate ones, and in one conversation a tool result that repeats chat text reaches the model twice. So:

- `get_turn_context` returns the assembled template and the state projection, with **no history by default**; in a single conversation the chat is the history. A separate `get_history` tool, or a `history` parameter (`none` or `inline`), serves separate chats.
- `submit_turn` takes the narration and changes (the same JSON as the API path) and returns a short ack, not the narration. The engine treats the submitted copy as canonical.
- **[Open]** Whether the pure template is better exposed as an MCP prompt than as a tool.

**[Decided]** The DM-MCP experience will differ from other providers: a model like Claude is freer and less constrained, may have Memory and other MCP servers enabled, and tool results are visible to the human in the client. In a single conversation this means GM-only state can be seen by expanding a tool call, so tenet 4 cannot be a hard guarantee there. This is accepted and must be documented as a limitation.

## Open

- **[Open]** Whether players ever get undo, and in what form.
- **[Open]** Pure template as an MCP prompt or a tool.
- **[Open]** Exact set of dev panels and tools for the first Textual release; start from the lists above and trim.
