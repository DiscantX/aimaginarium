# Multiplayer, server-client and the internal API

## Scope

**[Decided]** Single player first; the goal is also a party of 2 to 8 and, later, a massively multiplayer shared stateful world. Multiplayer and MMO design are **[Open]**: each needs a full discussion or two.

## Server-client

**[Open, leaning]** Ficus wants to look into a server-client model in which the server processes world events. Whether the client processes the player's turn, with the server validating, is undecided, and the number of API calls must be kept in check.

**[Proposed]** Make the **server authoritative**, as MMOs do: it owns world state, the event log, time, the director and every LLM call that produces truth; clients stay thin. In single player the server runs in-process behind the same API, so terminal, Textual, web and both MCP servers are all clients of one interface. The expensive resource is LLM calls, not network latency, so the real question is calls per turn (see [action-pipeline.md](action-pipeline.md)); this also answers "who commits": the server does.

**[Proposed]** Serialize commits per world (single writer per world or shard). That is easy for a party of 2 to 8; the hard part is the MMO.

## Internal API and MCP

**[Decided]** An internal API is the shared interface for every client. It is MCP-shaped so tools like Claude Desktop can use it.

**[Decided, considering]** Two MCP servers: one where Claude Desktop (or similar) acts as the dungeon master, and a separate one where Claude can be a *player*. Player interactions go through the internal API and are MCP-shaped.

**[Decided]** One API with `player` and `dev` roles; the build order, trace channel and dev tools are in [dev-tools-and-clients.md](dev-tools-and-clients.md).

**[Proposed]** The player-facing surface must be unable to return hidden state (see [time-and-knowledge.md](time-and-knowledge.md)); the player MCP server is the natural test of that.

## Open

- **[Open]** BYOK in a shared world: whose key pays for a world tick, the host's or the players'?
- **[Decided]** Distinguish **co-op** (one party, where spotlight matters) from **MMO-style** (a shared world where every player has agency).
- **[Decided, leaning]** Parties use **free-form scene** handling, because sequential and simultaneous turns only work for small parties and break down at MMO scale. A turn orchestrator for 2 to 8 players could be a later feature, and all three modes could in theory be offered and chosen at game start.
- **[Decided]** Deferred until single player is solid, but everything is built with multiple players in mind.
- **[Proposed]** Practical consequence for now: every action has an actor, and the server is the single writer.
- **[Open]** MMO world simulation when no players are present.
