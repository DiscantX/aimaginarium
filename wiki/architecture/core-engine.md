# Core engine and plugin layers

*Status tags (Decided / Proposed / Open) are defined in [../index.md](../index.md).*

## Governing principle

**[Decided]** The engine provides **mechanisms**; campaign design supplies **policy**. Chosen-one stances, strict declaration, journal visibility, reward style and similar questions are campaign or ruleset settings that the engine must be able to express, not hard-coded behavior.

## Table settings

**[Decided]** Table settings (content boundaries, tone, lethality, rules strictness and similar) are set at world creation and may be adjusted part way through. They are not placed in every prompt, to save context.

**[Proposed]** Settings live in the world record. Only those that differ from the default reach the prompt, as a line or two. Settings that code can enforce are applied by the ruleset and need no prompting. Provider-side content filters exist separately from player settings.

## Layers

1. **Core engine** (always present, whatever the story model).
2. **Ruleset plugins.** **[Decided goal]** D&D 5e SRD, a system-agnostic mode, and a free-form mode (no dice, story-centric, many guardrails off), behind a unified interface so a generic system can be plugged in or created on the fly. **[Proposed]** Rulesets and directors are separate plugin types, but some games couple them (Dungeon World's moves are rules and story direction at once), so the boundary needs care.
3. **Director plugins** (the modular story engine; see [../story/02-structure-and-direction.md](../story/02-structure-and-direction.md)). **[Decided]** Multiple versions can coexist.
4. **Campaign content and policy.**

## Core elements (draft)

**[Proposed]** What every story model needs, regardless of how the storytelling questions resolve:

1. **World state store.** Authoritative ground truth: characters, NPCs, factions, items, locations, relationships, inventory, effects.
2. **Event log with causal links.** Every state change recorded with its cause, in immutable commit order. Required for "because" and for consequences of omission.
3. **World time.** See [time-and-knowledge.md](time-and-knowledge.md).
4. **Knowledge layer.** What is true versus what each participant knows; the player sees only projections.
5. **Retrieval memory.** Qdrant for lore, past narration, summaries and past rulings, alongside the structured store.
6. **LLM gateway.** Provider abstraction (Gemini first), schema-enforced JSON, prompt assembly from state, tool calling, per-task model selection.
7. **Action pipeline.** See [action-pipeline.md](action-pipeline.md).
8. **Plugin contract.** Lifecycle hooks (time advances, action resolved, before narration, session start and end); what plugins may read and do (propose events, schedule things, add narration directives); plugin-owned namespaced state in the store.
9. **Internal API.** One surface for terminal, Textual, web and both MCP servers, with player and session identity built in. See [multiplayer-and-api.md](multiplayer-and-api.md).

Added later in discussion **[Proposed]**: the promise ledger and quest entries ([../story/05](../story/05-promises-and-quests.md)), effects on entities ([../story/04](../story/04-agency-and-tenets.md)), the sheet/chronicle split for characters ([../story/03](../story/03-character-desire-opposition.md)), a precedent log of rulings, and NPC knowledge with provenance.

## Other proposals

- **[Proposed]** A null director (pure causal simulation) is the first implementation; build the plugin interface from two real implementations.
- **[Proposed]** Replayability: the event log plus recorded dice allow a scenario to be replayed under different directors, which is how models are compared.
- **[Proposed]** Free-form mode loosens validation instead of bypassing it, so the event log stays complete in every mode.
- **[Decided]** Free-form and system-agnostic rulesets are first-class goals, so the unified ruleset interface must not assume dice or a numeric difficulty (see the tier translation in the action pipeline).
