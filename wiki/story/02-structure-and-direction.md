# 02 — Structure models and the director

*Storytelling lens 2, plus the question of how much the world may be steered for drama.*

## Structure models are lenses, not scripts

**[Proposed]** Freytag's pyramid, three-act structure, Campbell/Vogler's hero's journey, Truby's beats, kishōtenketsu and Propp's functions are **descriptive**: they were extracted from finished stories. Used prescriptively ("hit the midpoint at 50%") they become railroading in disguise and contradict the governing philosophy. Used as lenses they *diagnose*: a thread that has been flat for three sessions needs pressure; a thread that just peaked is due for fallout.

- The models disagree about what a story is. Freytag and the hero's journey are conflict-driven and protagonist-centered; kishōtenketsu (introduction, development, twist, reconciliation) needs no conflict and suits mystery, exploration or slice-of-life; Propp is closest to a grammar of functions.
- **[Proposed]** The engine offers a vocabulary of structural states (threads, phases, pressure). The campaign picks which lens applies, or none (free-form mode).
- **[Proposed]** Structure is multi-scale, like TV serials (episode, season, series): session, dungeon and campaign each have their own arc.

## How much may the world cheat for drama?

The central tension in the drama-manager literature (Façade, Left 4 Dead's director, Riedl's work):

1. **Strict causality.** The world runs purely on its own logic; drama is whatever emerges.
2. **Shaped timing.** The causal chain stays intact, but a director adjusts *when and how* things reach the player (what is surfaced, which rumor arrives first, which threat comes due while the player is nearby) without changing what is true.
3. **Interventionist.** The director may bend actual events to improve pacing, like a human GM fudging dice.

**[Decided]** Ficus leans toward shaped timing and interventionist, doubting that strict causality can be modeled well. These must be *settings*: switching both off should yield strict causality.

**[Proposed]** The causal simulation always runs and the director is an optional layer on top. "Interventionist" is a dial, not a switch. In strict mode the simulation itself must be rich enough to generate drama unaided, which is a tech-stack concern (see [../tech/tech-stack.md](../tech/tech-stack.md)).

## Offset cycles

Ficus recalls an essay or article by Margaret Weis and Tracy Hickman about writing the DragonLance novels, describing nested cycles: an outer cycle for the larger world and greater events, an inner cycle for the characters' immediate concerns, each sectioned into themes (romance, conflict, and others he does not remember), and offset from one another so they do not land at the same time. **The source has not been located** (a web search found nothing), so this is recorded as his recollection, not a citation. Related, documented ideas: medieval *entrelacement* (interlaced storylines) and the staggered A/B/C plots of serial television.

**[Proposed]** Model threads as cycles with a *period* and a *phase*. Flat stretches are what happens when every cycle is in its slow phase at once. "Shaped timing" then has a concrete meaning: adjusting phase offsets. The climax of a campaign is when cycles deliberately *converge*, which also restores unity of action across a sprawling world.

**[Open]** Whether a cycle represents a **scale** (world, region or faction, party, individual), a **theme** (romance, conflict, mystery), or a grid of both. Ficus is undecided.

## Modular directors

**[Decided]** The story engine should be modular within the core engine, so that different versions (cycles, countdown clocks, strict causality, and so on) can be swapped. This allows testing which models work best and supports different game types (a player could play a Dungeon World-like game or something entirely different).

**[Proposed]** The first implementation is a **null director** (no steering; pure causal simulation), which is also the strict-causality baseline. Build the plugin interface from two real implementations rather than one guess.
