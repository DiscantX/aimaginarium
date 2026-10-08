# Entity highlighting

*Design note. Status tags are defined in [../index.md](../index.md). Applies to the Textual UI and later the web UI; see [dev-tools-and-clients.md](dev-tools-and-clients.md).*

## What a color means

**[Decided]** The Textual UI colors player text and narrator text differently. Beyond that, certain words in the narration are colored. A colored word means one thing: **the thing exists in the world model beyond prose**, and the player knows about it. It carries no importance, no hint and no promise. Example: the narrator describes vines on a cavern wall and a sword and shield at the feet of a skeleton; the sword and shield are colored. The player cuts a piece off a vine, the engine creates an item, and in later narration "vine appendage" is colored too.

**[Decided]** Color is never used as an affordance hint. The ideas of a highlight-level setting (off, only things interacted with, everything known) and of creating entities generously so that scenery is tracked were both **rejected**: state must stay uncluttered, it would confuse the Chekhov's-gun tracking in the narrative layer, and coloring everything the player knows would color almost every noun. Players discover on their own that uncolored prose can be interacted with.

**[Open]** Watch in testing whether uncolored nouns discourage players from interacting with scenery. It is a risk for the possibility-space thesis and tenet 6, not a settled assumption.

**[Decided]** A plain on and off switch for highlighting is a user setting and UI choice, not an engine decision.

## Marking mechanism

**[Proposed]** Narration is stored as plain text, with no markup, so the model never sees tags in its history. Color is applied at render time.

**[Proposed]** The model returns a `mentions` field next to the narration. Each entry gives an entity (an existing id, or a reference to an entity created in the same turn's changes) and the phrase it used in this narration. The engine finds the phrase in the text and attaches the span. The entity type comes from the entity record, so the model cannot mislabel it.

**[Decided]** The phrase is the **bare noun or noun phrase, without articles**, never a sentence.

**[Decided]** No word-count cap: genuinely long names (an arcane book title, a whimsical invention) are common in fantasy.

**[Proposed]** Guards: a phrase is dropped silently if it is not found verbatim in the narration. Any phrase matching a known label or name is accepted at any length. A new phrase is rejected only if it spans a sentence boundary or covers most of a sentence, and unusually long new phrases are logged in the dev trace. Overlaps resolve longest match first.

**[Proposed]** Streaming: while narration streams, a deterministic matcher over known labels colors what it can. When the turn completes, mentions fix things up, including entities created that turn.

**[Proposed]** Every occurrence in a response is colored, not just the first. A partial scheme would make a second "sword" look different from the first and read as meaning something.

## Names and labels

**[Decided]** Philosophy: a name marks an identity, and too many names for one thing risk separating the identity from the name and leaving the player unsure whether it is the same thing seen before. So aliases are not collected automatically from prose.

**[Proposed]** Each entity has a **true name** (GM-side, possibly unknown to the player) and a **player label**, the one thing the player currently knows it by ("dull short sword", later "Breyor's Sword of Confusion +1"). The label changes only through engine events (identification, an NPC naming it, a rename), never through prose, so it also works per character in multiplayer. Old labels stay as historical matches so earlier history still highlights. The model supplies a label when it creates an entity. Prose variants such as "the blade" are ordinary words: they are colored through that turn's mentions but never stored as names, and the prompt shows only canonical names and ids, never an alias list.

**[Decided]** If two identical things could be confused, give each its own description at creation, and reuse that description for that thing while it is ambiguous.

**[Decided]** Once the player has identified a thing, it is called by its **name** whenever it is the focus of the narration (picked up, used, described) and on its first mention in each response. Afterwards "it" or a short form is acceptable within the same paragraph when nothing else could be meant.

**[Proposed]** Enforcement is soft: the mentions list shows which phrase the model used for an identified entity, so a mismatch is a warning in the dev trace, counted, and never a rejected turn.

## Color roles

**[Proposed]** Palette is defined as semantic tokens, mapped per UI and theme: `speaker.player`, `speaker.dm`, `system` (out-of-character), `roll`, `dev`, `retracted` (grey, layered over the original role), and the entity tokens. Highlighting also uses a second cue (underline or bold) so it does not rely on color alone.

**[Open]** One highlight color for any known entity, or a color per entity type (character, location, item, faction)? Per type is more informative but needs a palette that holds in light and dark themes; a single color is simpler.
