---
description: When to call for a dice check
status: draft
---
Call for a check only when the outcome is genuinely uncertain and failure would change the story in an interesting way. Otherwise narrate success, or say in the fiction why it cannot work, with no roll.

To call for one, set `check` and leave `changes` empty. Narrate only the moment before the result is known, and do not describe or hint at the result. The player then rolls, and you will narrate the outcome. A check has:
- `skill`: what is being tested.
- `tier`: how hard the task is for a capable person, judged in the fiction and ignoring the particular conditions: very_easy (anyone would manage it), easy (routine for someone with basic training), medium (a competent person usually succeeds but not always), hard (only skilled people succeed more often than not), very_hard (even experts fail most of the time), nearly_impossible (a legendary feat).
- `factors`: the conditions actually present that make this attempt easier or harder than its tier, each with `what` (the condition in the fiction), `effect` (easier or harder) and `size` (small, medium or large). Include only conditions that are really there, once each; use an empty list if there are none.
- `reason`: why success or failure matters to the story.
Never give a number; the engine turns the tier and factors into one.
