# Action pipeline

*How a player's turn becomes committed state.*

## Who commits state

**[Decided]** Working assumption: the **LLM proposes, the engine validates and commits**, with **one LLM call per player turn in the common case**.

## Validation versus adjudication

**[Proposed, not contested]** Two jobs are easily confused. *Validation* asks whether a proposal is consistent. *Adjudication* asks whether an action is possible in the fiction. Code can do the first, not the second.

| Layer | Example | Who checks |
|---|---|---|
| Structural | Valid JSON, referenced IDs exist | Code |
| State consistency | Player owns the item, target is in the scene, HP not negative | Code, against the store |
| Rules legality | Spell slot available, range, action economy | Ruleset plugin (absent in free-form) |
| Fictional feasibility | Can I swing from the chandelier? | The LLM |

The LLM is the GM and adjudicates; the engine is the bookkeeper and catches mechanical errors (granting an item that does not exist, killing someone already dead). A second LLM call to re-judge feasibility is not planned. Scrutiny can be proportional to stakes: reversible low-stakes changes commit freely, permanent or world-level ones may warrant an optional second-opinion call, off by default.

## When a check is called for

**[Decided]** A check is called for only when failure would change the story in an interesting way and the outcome is genuinely uncertain. Otherwise the DM narrates success, or says the action cannot work, with no roll. The LLM makes this call in call 1, informed by the precedent log. (Ficus notes this is more or less standard DM practice.)

## Check turns

**[Decided]** Turns that need a dice check use **two LLM calls**; turns without a check use one.

1. **Call 1.** The LLM narrates the setup and emits a structured request (check needed, skill, difficulty). The engine validates and commits the ruling *before* any roll, so the difficulty cannot be adjusted after seeing the result.
2. **The player rolls.** **[Decided]** The player rolls their own dice and makes their own skill check; the roll is always shown, as a number. An auto-roll option is a minor extra. **[Proposed]** The roll is generated in code and logged; the client's button press requests the reveal and is not a source of randomness.
3. **Call 2.** **[Decided]** The prompt varies with the outcome: a natural 1, a barely-passed roll and a natural 20 each feed a different instruction. The ruleset classifies the result (critical failure, failure, narrow success, success, critical success, margin) and the engine selects the matching instruction. The LLM narrates the result and proposes state changes; the engine validates and commits.

**[Proposed]** This maps onto function calling (`request_check` tool call, engine pauses, tool result carries the roll and its classification). Call 2 reuses most of call 1's context, so provider-side caching may make it cheaper; verify for Gemini. The dice animation and streaming the setup narration hide latency. An "outcome bands" variant (one call returning narration for each band) remains a fallback where the game cannot pause.

**[Decided]** Different models can serve different tasks, configurable at the server level (for example a smaller model for the check ruling in call 1).

## Difficulty numbers

**[Open]** Ficus asked how the target number is decided and how to avoid the same number per tier. **[Proposed]** answer:

- The LLM does not output a raw number (models anchor on familiar values, and a number means nothing outside its ruleset).
- It outputs a **tier**, defined in the fiction, plus a short list of **difficulty factors** (direction and size: rain-slick, no tools, guards nearby).
- **The ruleset translates** into its own mechanic: a 5e DC, a band, a number of successes. Code applies the factors to the tier's base, giving varied, explainable numbers.
- Factors double as the **dependencies** of the precedent log. Whether the target is shown to the player before rolling is a setting.

## Precedent log

**[Decided]** Rulings are stored so that adjudication stays consistent across sessions, with a rationale for why an action failed or was impossible. Skill and circumstances change (a lockpicking skill has risen), so the LLM decides whether anything has changed enough to allow another check.

**[Proposed]** Store both a prose rationale (for the LLM) and structured dependencies (state facts the ruling relied on, with their values at the time). If no dependency changed, reuse the precedent with no LLM call; if one changed, give the LLM the precedent plus the changed facts and let it decide. This matches the tabletop convention that a failed check cannot be retried unless circumstances change. Look precedents up by exact entity and by similarity (Qdrant). The brake against "yes-machine" drift is the check itself, **[Proposed]** measured by logging tier and outcome distributions in testing.

## Context assembly

**[Proposed]** Each call includes a compact summary of the player's capabilities and the established properties of what they carry, so the LLM can recognize creative uses of items it was never planning for.
