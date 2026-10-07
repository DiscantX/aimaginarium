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

**[Decided]** Different models can serve different tasks, configurable at the server level (for example a cheap model for summaries and a strong one for world ticks). Call 1 is the `narrate` task and carries any check request, so the check ruling uses the narration model; there is no separate check task. Call 2 is `check_outcome`. See [../tech/llm-gateway.md](../tech/llm-gateway.md) for tasks and fallback.

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

## As built in the terminal prototype (#16)

*Status tags do not apply: this records what the code does today.*

`aimaginarium/engine/game.py` holds `Game`, a **temporary** in-process facade (`open_scene()`, `take_turn(actor, text)`), and `aimaginarium/cli.py` is the terminal client. Run it with `python -m aimaginarium` after copying `aimaginarium.example.toml` to `aimaginarium.toml` and putting the key in `.env`. A new world file starts as a hand-made demo world (a tavern, a square, Kael and Marta).

A turn is an async stream of events. After a `CheckCalled` event the generator waits until the client resumes it, which the terminal does when the player presses Enter; the roll is precomputed, so the button is cosmetic. The roll shown is die, modifier and total, never the difficulty.

1. The player's input is logged (`player.action`, actor = the character).
2. Call 1 (`narrate`) streams narration. The reply is lenient to parse: JSON that does not match the plan's paragraph count still works, because the plan is enforced by the provider's schema rather than by the engine. The call is logged (`llm.call`: recipe, variant, fragment hashes, model, usage including time to first token and cached tokens).
3. No check: the proposed changes are validated and committed with actor `gm`, caused by the action.
4. Check: `check.requested` is committed before the roll; changes in a check-bearing call 1 are not committed. The roll is logged (`roll`), then call 2 (`check_outcome`) is made with call 1's request and narration as its prefix, the outcome instruction chosen by the roll's classification, and its changes are committed with the roll as their cause.
5. A rejected commit writes nothing but `changes.rejected` (errors and proposed changes) and tells the player; an unreadable reply or an unavailable provider writes `reply.invalid` or `llm.failed` and leaves the world unchanged.

Rules are a minimal d20 stand-in (`D20Rules`): natural 1 and 20 are critical, a success by fewer than 3 is narrow. Skills come from `data.sheet.skills` on the character.

**Not built yet** (each its own issue): the repair call for rejected changes (the narration the player saw can currently disagree with the world); persistent conversation history (it is in memory, so a restarted game continues without it); player-facing projections of facts (the narrator sees secrets, marked with who knows them); background commits while the player reads; any director other than the null one.
