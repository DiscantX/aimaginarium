# 07 — Interactive narrative literature

> **Draft notes, not yet discussed.** Written by Claude without prior discussion. Nothing here counts as agreed except where it restates something Ficus stated; everything else is a suggestion to be promoted, changed or dropped.

*Storytelling lens. Status tags are defined in [../index.md](../index.md). Source confidence is noted at the end: some sources were checked on the web this session, others are recalled from memory and not re-verified.*

## The core problem

**[Proposed]** The field's central tension is the one our tenets already name: a coherent, dramatic story versus real player agency. Riedl and Bulitko's survey defines interactive narrative as an experience in which the user's actions can significantly alter the direction or outcome of the story, and reviews about twenty years of AI work on it. The literature calls the conflict between player freedom and authorial intent the *boundary problem* (also the *narrative paradox*). Our governing philosophy ("the world has momentum; the player has leverage", [01](01-what-is-a-story.md)) is one answer to it: author the possibility space, not the plot.

## Three families of approach

**Drama management ("strong story").** An omniscient, disembodied agent watches the world and nudges it toward a good story. Bates proposed the idea in the early 1990s; *experience manager* is the later generalization. The manager usually looks ahead through possible sequences and picks one that scores well against some narrative aesthetic.
- **Façade** (Mateas and Stern, released 2005) is the reference implementation. Content is cut into *beats*: small, interruptible scenes with preconditions and effects on story state. The drama manager picks beats against a desired tension curve, aiming at rising tension and a climax. The authoring cost is the lesson: hand-writing enough beats for a free-roaming player is the bottleneck.
- **Left 4 Dead's AI Director** (Booth, Valve, 2008) is the commercial relative. It paces threats, spawns, audio and item drops from the players' observed state to produce build-up, peak and relief. Booth's design lines worth keeping: treat the whole party as one player, and "low probability plus high drama is memorable".

**Emergent narrative ("strong autonomy").** No manager; characters with goals and beliefs act, and story is whatever emerges. Tale-Spin (see [03](03-character-desire-opposition.md)) is the classic cautionary case: goals pursued without drama. Later systems add social state (Versu, Prom Week) or LLM-driven memory and planning (Park et al.'s *Generative Agents*, 2023).

**Hybrids.** Riedl's comparison of approaches argues that a drama manager layered over autonomous characters can outperform either alone, at the cost of coordinating them. His work with Stern names the specific conflict: an NPC's own goals can collide with the manager's plot.

**Storylets and quality-based narrative.** Narrative is assembled from discrete, reorderable chunks, each gated by preconditions over world *qualities* (variables). Emily Short's "Beyond Branching" separates quality-based, salience-based and waypoint structures; Failbetter's Fallen London popularized quality-based narrative. Kreminski and Wardrip-Fruin (ICIDS 2018) map the design space along several dimensions, including how preconditions are defined, whether a storylet can repeat, and what a storylet contains.

## What this means for us

1. **[Proposed] We are a hybrid by construction.** The causal simulation is the autonomy layer; the director is the optional manager on top. This is already the structure in [02](02-structure-and-direction.md); the literature supports it and tells us to expect the coordination problem.
2. **[Proposed] The LLM changes the authoring bottleneck.** Façade's limit was hand-authored beats. Here the content of a scene is generated, so the director's job shrinks to choosing *what situation to bring about and when*, which is the generative drama management idea in the literature. The risk moves from authoring cost to the failure modes in [06](06-llm-failure-modes.md).
3. **[Proposed] Storylets are a director vocabulary, not a menu.** A storylet is preconditions over world state plus a situation specification plus effects. Used as a *world-side* repertoire, they let a director pick the next situation by salience (what fits the current state), with the LLM generating the content. Used as Fallen London uses them, as cards offered to the player, they violate tenet 6 (no menus), so we must not.
4. **[Proposed] A tension variable gives shaped timing a measurable target.** Left 4 Dead's curve is shaped timing in the sense of [02](02-structure-and-direction.md): the director changes *when* things reach the player, not what is true. For an LLM DM the intensity estimate could come from state (health, threats nearby, recent outcomes) or from an LLM rating. This is the cheapest real director to build and a good second implementation after the null director.
5. **[Proposed] Director interventions are recorded.** The manager-versus-character conflict is resolved by a rule: NPCs act on their own beliefs and desires; the director may change timing and what information propagates, and under the interventionist setting may change events, but every such act is logged as director-caused. Switching the director off then reproduces strict causality, which is the setting [02](02-structure-and-direction.md) requires.
6. **[Proposed] Party play inherits Booth's rule.** Pacing a party means treating it as one player for tension purposes, while agency stays individual.
7. **[Proposed] LLM DM research so far leans toward assistance.** CALYPSO (Zhu et al., AIIDE 2023) built LLM tools for *human* DMs, who valued polished text they could use directly and rough ideas they could develop, while keeping creative control. That is relevant to the MCP design (Claude as DM, Claude as player) and raises an open possibility of a human-DM-assisted mode.
8. **[Proposed] Agency has a recognizable shape.** Murray's framing (agency, immersion, transformation) treats agency as the player seeing results that visibly follow from their choices. This is the positive form of consequence of omission ([01](01-what-is-a-story.md)) and of the no-softening rule in [06](06-llm-failure-modes.md).

## Candidate directors

**[Proposed]** For the "build the plugin interface from two real implementations" plan ([02](02-structure-and-direction.md)):

| Director | Idea | Cost | Source |
|---|---|---|---|
| Null | Pure causal simulation | Lowest | Baseline |
| Tension-curve pacer | Estimate intensity, shape the timing of threats and information | Low | Left 4 Dead |
| Salience/storylet | Select situations by preconditions over world state, LLM generates content | Medium | Short, Kreminski |
| Look-ahead drama manager | Search future sequences against a narrative aesthetic | High | Bates lineage, Façade |
| Offset cycles | Threads with period and phase | Medium | Weis/Hickman recollection, [02](02-structure-and-direction.md) |

## Open

- **[Open]** Tension: computed from state, estimated by the LLM, or both, and who tunes it?
- **[Open]** Which director is the second implementation: the tension pacer (cheapest) or the storylet/salience director (richest)?
- **[Open]** Whether a human-DM-assisted mode belongs in scope.
- **[Open]** How a director's interventions interact with the player-never-loses stance ([04](04-agency-and-tenets.md#failure-and-recovery)).

## Sources and confidence

Checked on the web this session: Riedl and Bulitko, "Interactive Narrative: An Intelligent Systems Approach," AI Magazine 34(1), 2013; Riedl and Stern on believable agents and drama managers (TIDSE 2006); Mateas and Stern on Façade; Kreminski and Wardrip-Fruin, "Sketching a Map of the Storylets Design Space," ICIDS 2018; Short on storylets; Booth's Left 4 Dead interviews and GDC coverage; Zhu et al., CALYPSO, AIIDE 2023.

Recalled from memory, not re-verified here: Bates's original drama-manager proposal, Weyhrauch's search-based drama management, Versu, Prom Week, Park et al. *Generative Agents*, Murray's *Hamlet on the Holodeck*, Aylett's emergent narrative and the narrative paradox. The fourth storylet dimension in Kreminski and Wardrip-Fruin was not confirmed. The Weis/Hickman essay remains unlocated.
