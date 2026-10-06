# World time and the knowledge layer

## World time

**[Open, partly proposed]** Ficus's requirement: the engine supports fantasy and sci-fi settings in which time travel, slowing of time and similar effects change temporal state. Location is already non-linear (any direction, even teleport), and time should be treated the same way: state that rules may change arbitrarily.

**[Proposed]** Separate three things that "time" conflates:

1. **Commit order.** The order in which the engine recorded events: forward-only, immutable, the ground truth for replay.
2. **In-world time.** Where an event sits on the setting's calendar: *data* attached to events and entities, which can be anything.
3. **Causal links.** Which event caused which.

Weird time then becomes data and rules rather than a structural problem.

- **Time frames.** Each region, plane or entity maps to a clock with a rate and offset against the global tick. The default is one frame at rate 1. A Feywild where a night is a hundred years is another frame. Effect durations tick in the target's frame.
- **Time travel comes in three flavors** and the campaign picks: a fixed timeline (the traveler can only fulfill the past), a mutable timeline (events rewritten, with the change recorded), or branching timelines. Branching is the expensive case and one of the few scenarios where version-style storage (for example TerminusDB) could earn its place; see [../tech/tech-stack.md](../tech/tech-stack.md).
- **Lazy catch-up simulation.** Do not simulate every region every tick with an LLM. Advance a region on demand when the player touches it, computing what happened over the elapsed span with cheap deterministic updates and reserving LLM calls for the few significant threads. This also serves the call-count concern and the shared-world case.

## Knowledge layer

**[Decided]** The GM always knows more than the player. Decisions can happen behind the scenes that the player is not aware of.

**[Proposed]** The engine's ground truth is always a superset of what any participant knows, and everything a player sees is a **projection**. It is a hard boundary: the player-facing API must be structurally unable to return hidden state. A Claude-as-player MCP server is a good test of this boundary. Knowledge splits between *characters* (in-fiction) and *players* (out-of-fiction), which matters in a party.

- Perception effects (blindness, deafness) change the projection.
- NPCs and factions hold beliefs with provenance, and may only act on what they could have learned in-world (see [../story/03](../story/03-character-desire-opposition.md)).
- Information propagation (rumors, messengers, evidence) is how the world's offscreen events reach the player (see [../story/01](../story/01-what-is-a-story.md)).
- The quest journal, if shown, is a projection of what the character understands (see [../story/05](../story/05-promises-and-quests.md)).
