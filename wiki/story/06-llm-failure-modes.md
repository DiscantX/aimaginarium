# 06 — LLM failure modes

> **Draft notes, not yet discussed.** Written by Claude without prior discussion. Nothing here counts as agreed except where it restates something Ficus stated; everything else is a suggestion to be promoted, changed or dropped.

*Storytelling lens (numbered by completion order). Status tags are defined in [../index.md](../index.md).*

## Why this lens

**[Proposed]** The other lenses say what a good story and a good GM do. This one asks how an LLM in the GM seat will fail at it, so the architecture can be built to expect those failures. Most mitigations already live elsewhere in the wiki; this essay indexes them, adds the missing ones, and defines how we *detect* failure, since prompt discipline cannot be policed by code alone (see [04](04-agency-and-tenets.md)).

## Failure modes and where each is handled

| # | Failure | Symptom | Mitigation | Status |
|---|---|---|---|---|
| 1 | **Yes-machine** | Every creative idea works | The check itself is the brake: the LLM rules a tier, code rolls ([action pipeline](../architecture/action-pipeline.md)). Measure tier and outcome distributions. | Decided (checks as the answer); measurement Proposed |
| 2 | **Authoring the player** | "You step forward and draw your sword" | Flavor-versus-decision test, structural rule that player-character events come only from that player's declared action ([04](04-agency-and-tenets.md)). | Existing |
| 3 | **Menus and railroading** | "You could A, B or C"; heavy-handed hints | No field for options in the output schema; responses end with a synopsis and an open question; "how?" for consequential ambiguity ([04](04-agency-and-tenets.md)). | Stance Decided; schema mechanism Proposed |
| 4 | **State drift** | Dead NPC returns; item changes hands unannounced | Engine owns state; LLM proposes, engine validates and commits ([action pipeline](../architecture/action-pipeline.md)). Each call gets a state projection, not a model-written recap. | Decided / Proposed |
| 5 | **Invented entities and gear** | Item in the pack that does not exist | Validate item and entity references against the store; new entities only via explicit schema fields so inventions are visible ([04](04-agency-and-tenets.md)). | Existing / Proposed |
| 6 | **Hidden-state leakage** | Narration reveals a secret; NPC exploits an unlearned flaw | Knowledge-basis facts for NPC proposals ([03](03-character-desire-opposition.md)); narration prompt receives the player projection only ([time and knowledge](../architecture/time-and-knowledge.md)). | Decided / Proposed |
| 7 | **Forgotten or orphaned setups** | Planted detail never pays off, or payoff without setup | Promise ledger and overdue-promise queries ([05](05-promises-and-quests.md)). | Proposed |
| 8 | **Number anchoring** | The same target number every time | Tier plus difficulty factors; the ruleset translates ([action pipeline](../architecture/action-pipeline.md)). | Open (confirm) |
| 9 | **Significance inflation** | Every inspected detail is a plot hook | Engine-set significance with mundane as the default ([05](05-promises-and-quests.md)). | Proposed |
| 10 | **Mode collapse** | Cozy taverns, monologuing villains, repeated names and phrasings | Outcome-varied prompts (Decided). New: recent-phrasing and name-reuse hints in the prompt; tone guidance from the director. | Mixed; new part Proposed |
| 11 | **Consequence softening** | The model quietly shrinks harm: the trap only startles, the blow glances, the betrayal is forgiven | The engine fixes severity before narration (the tier and the roll decide how bad it is) and commits the resulting state changes; log intended severity against applied severity. This is separate from recoverability (see below). | Proposed |
| 12 | **Format failure** | Invalid or truncated JSON, missing fields | Schema-enforced output (Decided, likely); validate, retry with the error, optional fallback model after N failures. | Decided / Proposed |
| 13 | **Long-context degradation** | Early facts ignored as the prompt grows | Compact, relevant context assembly; retrieval instead of full history ([action pipeline](../architecture/action-pipeline.md)). | Existing |
| 14 | **Provider variance** | Behavior shifts between models and versions | Provider abstraction plus the evaluation suite below; pin model versions per campaign where the provider allows. | Proposed |

## Softening versus recoverability

**[Decided]** The player never truly loses: there is always a way to recover and continue, unless the campaign sets a permadeath mode. See [04](04-agency-and-tenets.md#failure-and-recovery).

**[Proposed]** Failure mode 11 is *not* the opposite of that stance. Softening is the model shrinking a consequence after the fact, which makes stakes feel fake. Recoverability is a property of the world after a full-size consequence has landed: the harm is real, the cost is real, and a path forward still exists. The first is an LLM failure to prevent; the second is a design guarantee to provide. Keeping them apart means a hard consequence is never traded away to keep the game going.

## Detection

**[Proposed]** Failure modes 2, 3, 6, 9, 10 and 11 cannot be caught by schema or state validation, so they need a standing evaluation suite, with scripted scenarios aimed at one failure mode each, automatic checks where code can judge, and replay under different models and directors. **[Decided]** The suite does not live in the storytelling essays; it is specified in [../tech/evaluation-and-replay.md](../tech/evaluation-and-replay.md).

## The local model option

**[Decided]** A local model (Ollama) is a candidate provider alongside Gemini and other API providers. The repo already has a working runner and sample (`local_llm/`), verified working with a manageable response time. **[Open]** Output quality is untested.

**[Proposed]** Consequences for the design:

- **One provider interface.** The gateway must not assume Gemini's schema enforcement, caching or function calling. Each provider declares capabilities and the gateway adapts, with validate-and-retry as the common floor.
- **Schema enforcement differs.** The sample uses Ollama's plain JSON mode, which guarantees syntax only. Whether the installed Ollama version accepts a full JSON schema needs verifying.
- **Caching differs.** The two-call check turn assumes cheap reuse of call 1's context; a local runtime may behave differently.
- **Task fit.** Small local models are most plausible for the check ruling, which is mostly classification, and least proven for full narration. Per-task model selection (Decided) is the natural place to test this.
- **Test the question empirically.** Run the [evaluation suite](../tech/evaluation-and-replay.md) against the local model and an API model, and compare failure rates by mode. Expect the structural modes (5, 12, 13) to show the widest gaps.

## Open

- **[Open]** Local model quality for each task, pending the suite.
- **[Open]** Which failure modes the campaign may choose to tolerate (the yes-machine may be fine in a free-form game).
