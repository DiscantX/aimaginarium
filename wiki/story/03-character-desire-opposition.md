# 03 — Character, desire and opposition

*Storytelling lens 3.*

## Desire as data

**[Proposed]** A story is a character pursuing a desire against opposition, and it can only be as compelling as the opposition is strong. A character's *want* (conscious goal) differs from their *need* (what they actually require); the gap creates depth. Character is revealed by choices under pressure.

- Desire is first-class data for player characters, NPCs and factions: goals, what blocks them, resources, methods. Tabletop systems already encode this for players (5e ideals/bonds/flaws, Fate aspects).
- NPCs act on **beliefs**, not on ground truth (the belief-desire-intention model from AI). Beliefs are a possibly wrong subset of truth, which yields deception, misunderstanding and dramatic irony from the knowledge layer.
- The director's central job is **matching opposition to desire**: too weak and the story is flat; too strong and the player is frustrated.
- *Caution:* Tale-Spin (1976), an early goal-driven story generator, is remembered for how its simulated characters pursued goals without producing drama. Simulated desire is necessary but not sufficient, which is the case for a director layer.
- Choices need weight: record what each choice *cost*, not only what happened.

## NPCs only know what they could learn in-world

**[Decided]** An NPC may exploit a character's trait only if it could have learned it through in-world means. The steward can know Kael served in a given regiment (tabard, reputation); he cannot know it rattles Kael until Kael has shown it.

**[Proposed]** Enforcement: any proposal in which an NPC exploits a trait must cite a *knowledge-basis fact* in that NPC's knowledge layer, and the engine rejects it if none exists.

## Flaws are recognized, not enforced

**[Decided]** Force is off the table (see [04](04-agency-and-tenets.md)). Compels (a priced offer made before the choice, as in Fate) are not chosen, because they require presenting the player with options. The world may *pressure* a character, and subtle hints in the prose are acceptable, but the engine must never tell the player "you can't ignore the insult."

**[Decided]** 5e-style Inspiration is probably the best fit for rewarding play to a flaw, because the reward arrives *after* the choice. How the reward arrives needs care, and it must fit the ruleset plugin architecture.

**[Proposed]** Details:

- Recognize **engagement** with a motivation (honored, defied, or overcome at real cost), not obedience. Overcoming a flaw is an arc beat.
- No penalty for ignoring a flaw. The world simply reacts to what the character actually did (word spreads that Kael swallowed the insult).
- Anti-farming: a cap (5e's single Inspiration) and awarding only when engagement cost the character something.
- Deliver the reward outside the fiction, as a brief note with a one-line reason.
- Pattern shared with difficulty tiers: **the LLM judges in fictional vocabulary, the ruleset translates into mechanics, the engine commits.** The LLM emits "motivation X engaged, at low/medium/high cost"; 5e grants Inspiration, Fate a fate point, other systems XP, free-form nothing mechanical.
- Note: the exact Inspiration text differs between SRD versions; check which one we build on.

## Characters evolve

**[Decided]** If a player's decisions contradict the initial character sheet, that may be a character arc, not out-of-character play.

**[Proposed]** Keep two records. The **sheet** is what the player says the character is: player-owned, changed only with consent, with the engine proposing revisions at quiet moments such as session boundaries. The **chronicle** is what the character has actually done and what the world believes: engine-maintained. Reputation and NPC knowledge draw on the chronicle, never the sheet.

## Open

- **[Open]** Reward notice timing: immediate (teaches the system, can feel gamey and interrupts immersion) or quiet accrual with a session-end recap (protects immersion, but a misjudged award cannot be corrected in the moment).
- **[Open]** How individuals shape faction qualities. Candidate models: dominant leader; weighted aggregate of members; hierarchy where dissent and defection generate plot.
