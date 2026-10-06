# 05 — Promises, setups and quests

*Storytelling lens 4 (setups and payoffs, Chekhov's gun) and the quest model.*

## Promises

**[Proposed]** Chekhov's principle says a planted element should earn its place. Barthes' two codes give a sharper form: a story runs on **enigmas** (questions posed, answers delayed) and **action sequences** (things begun that create an expectation of completion). Each is a debt. Mystery craft adds *fair play* (clues available before the reveal), which tabletop practice turns into the **three-clue rule**: give several independent ways to reach a needed conclusion so no single missed clue stalls the game.

In a sandbox the player chooses which threads to pull, so the principle is restated: **the world never forgets a promise it made, but the player may decline to collect.** Unpulled threads keep resolving offscreen, so the gun still fires without the player.

**[Proposed]** A **promise ledger**: each planted element is recorded with what was planted, when (commit order and world time), who knows, and a status (dormant, active, paid, subverted, abandoned). It counters the LLM's habit of forgetting its own setups and lets a director query for *overdue* promises, which similarity search alone cannot do. Promises come from two sources: deliberate (planted by the director) and **emergent** (a detail the LLM improvises while narrating, which the player may seize on). The LLM can flag details as notable in structured output.

## Quests

**[Decided]** A quest list exists. Quests are loose guides and need not be followed. Whether the list is presented to the player is optional (a game or user setting). **[Proposed]** The campaign sets the ceiling and the user chooses within it. The journal shows only goals as the *character* understands them, which may be incomplete or mistaken.

**[Decided]** When the story presents a goal, the LLM creates a quest with an end goal. Alternative **routes are not predefined**: the possibilities are endless, only meeting the goal matters, not how, and the player may use something unplanned (a magic mirror found on another quest). At most a few affordances are seeded in the fiction (someone mentions a boat headed that way).

**[Proposed]** Shape of a quest: a **goal predicate** worded as an *outcome* ("the dragon no longer threatens the village", not "the dragon is slain"), **stakes and links** to the entities involved, and a **status** (offered, adopted, resolved, world-resolved). **Obstacles live in the world**, not in the quest: the sea, the guards, the locked door are world facts with their own state, and progress is derived from world state. A quest is a typed entry in the promise ledger; many promises never become quests.

**[Proposed]** Seeded affordances exist for fairness, not as a solution set: a solvability check at creation, and a stuck-detector that seeds more if the player runs out of ideas. Unplanned routes are judged by the normal pipeline: the LLM adjudicates feasibility from the established properties of what the player carries, the engine validates consistency, and the quest layer notices that state changed. Every call therefore needs a compact summary of the player's capabilities and established item properties.

**[Proposed]** Lifecycle: a quest is *offered* by the story but *adopted* by the player's action or declaration; unadopted quests remain world threads. Outcomes include **world-resolved** (the dragon razed the village while the player dithered). A goal can be met while the world thread continues (a charmed dragon leaves, but still exists with motivations). Quests can nest ("defeat the lich" parents "find the phylactery"). Only the player-facing projection is shown, never the GM's view.

## Player attention gives meaning to details

**[Decided]** Player attention may give meaning to details; the GM crafts the story around player actions, otherwise the player must guess some obtuse correct action. If the player inspects something and passes the check it can become of interest, **but this is restricted**: a successful inspection need not reveal significance ("you confirm that it is indeed a regular stone").

**[Proposed]** Mechanisms:

1. **Boundary:** attention may decide the truth of *uncommitted* details; it never overwrites committed facts. Backbone threads (the big bad, faction plans) stay the world's.
2. **Bind, don't invent:** prefer attaching an anchored detail to an existing open promise whose theme fits; new threads are created only deliberately.
3. **Significance is its own variable, controlled by the engine:** before narration, code sets the detail to mundane, minor or significant from a distribution that depends on campaign tone and recent discovery pacing, and passes it into the prompt like an outcome band. **Mundane is the default**, and the prompt gives the LLM permission to be boring.
4. **Perception and significance are separate:** the skill check decides whether the player perceives what is there; the significance roll decides what is there. The truth is committed at first examination, so a failed check does not decide the detail is mundane.

**[Proposed]** Fuller direction for later: detail stubs. Committed entities are the goal-bearing ones (the dragon is created in full with motivations); route-like entities (the boat, the key) are stubs with a name, a location and tags, fleshed out on first engagement.

**[Open]** Tuning the significance distribution and its pacing rule.
