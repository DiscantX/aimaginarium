# 04 — Player agency and narration tenets

*Rules about what the engine and narrator may and may not do to the player.*

## The tenet

**[Decided]** The engine/GM must **never make actions or decisions for the player**. It only says what happens *after* the player has made a decision. This tenet must always be followed.

## No menus

**[Decided, leaning]** Do not present the player with a list of options, potential outcomes or consequences. At most, a response ends with a short synopsis of the scenario and a question like "what do you do?" Consequences exist, but the player finds out when they occur.

**[Proposed]** Distinguish *signals about the world* from *consequences of options*. "The smoke on the horizon is thicker than yesterday" is information and is allowed; "if you don't go now, the village burns" is a menu and is not. This keeps fair telegraphing (see [01](01-what-is-a-story.md)) without listing choices.

## Flavor versus decision

**[Decided]** Flavor such as "your hand tightens on your hilt" is welcome. Prose should not be policed too strictly.

**[Proposed]** Working test: *flavor leaves the player's next move open; a decision commits the character or changes state the player would have wanted to decide* ("Kael draws his sword"). The world owns the player character's body and circumstances (the arrow hits your shoulder); the player owns choices, words and inner state.

**[Proposed]** Enforcement: structurally, an event whose actor is a player character is accepted only as the result of that player's declared action. Prose-level conduct is prompt discipline plus an evaluation suite, since code cannot reliably police it.

**[Decided]** Subtle hints in the prose reminding the player of a flaw are acceptable. **[Proposed]** Those hints should live in the world and in NPC behavior, not in the player character's head.

## Ambiguous actions

The problem: "I attack the orc" without saying how. Fists, equipped sword, spell, thrown rock?

**[Decided]** When an action is *consequentially* ambiguous, the engine asks **"how?"** with no options listed. It gives a small amount of guidance on what to input next without railroading.

**[Proposed]** Supporting rules:

- Defaults may honor *prior player decisions* (the readied weapon), because that is not the engine deciding. Defaults never spend limited resources (spell slots, consumables, unequipped items) by assumption.
- A player-declared default attack on the sheet.
- A punitive default (attack with fists, causing failure) is rejected because it is the engine deciding for the player and penalizes terseness, not skill. **Strict declaration** may exist as an optional campaign-level setting.
- Check weapons and items mentioned in LLM output against inventory to catch invented gear.

## Effects on the player

**[Decided]** Mind-affecting effects are generalized, and the engine tracks effects the player is under (movement restrictions, mental impairment, and so on).

**[Proposed]** An effect is a record with source, target, duration, tags and a constraint that the ruleset translates into mechanics. Active effects go into every prompt. Durations tick in the target's own time frame (see [../architecture/time-and-knowledge.md](../architecture/time-and-knowledge.md)). Perception effects change the projection the player receives (a blind character is not given visual description). Effects **interfere with a declared action after it is declared** ("you try to strike, but your arm will not obey") and never pre-empt it.

## Failure and recovery

**[Decided]** The player never truly loses. There is always a way to recover and continue, unless the campaign sets a permadeath mode. Consequences are still real (see [06](06-llm-failure-modes.md#softening-versus-recoverability)); recoverability is a property of what the world offers afterward, not a reduction in what happened.

**[Decided]** What recovery looks like is situational and world-dependent, and will be tuned in testing. The AI decides how it happens, in a way that fits the story: resurrection, escape, someone bailing the player out. Resurrection needs a god or mechanism in the world. Recovery must be plausible and explained, never hand-waved ("the local priest resurrected you, carry on").

**[Proposed]** To make "explained" checkable, the AI's recovery cites something that already exists in the world (the god, the rival who wants the player alive), and the engine validates that it exists. To be settled in the pipeline discussion.

**[Open]** The range of defeat outcomes the engine must be able to express (capture instead of killing, rescue, a costly revival, a setback in standing or resources). This is mostly campaign policy. It also interacts with world-resolved outcomes (the village burned while the player dithered): the world can lose something permanently while the player can still continue.
