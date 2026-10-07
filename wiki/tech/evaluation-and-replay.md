# Evaluation and replay

*Tooling essay. Status tags are defined in [../index.md](../index.md). Split out of [story/06](../story/06-llm-failure-modes.md) because it serves the whole engine, not only storytelling.*

## Purpose

**[Proposed]** Several design questions can only be answered by running the engine: which model handles which task, whether a director setting improves play, whether a local model is good enough, whether a prompt change fixed or broke something. The suite turns those into repeatable measurements.

## Parts

- **Scenario cases.** Short scripted situations, each aimed at one failure mode from [story/06](../story/06-llm-failure-modes.md): the impossible claim, the unowned sword, the ambiguous attack, the invitation to reveal a secret, the dithering player whose village should burn, the failed check that tempts the model to soften harm.
- **Automatic checks** where code can judge: schema validity, references against the state store, player-authored events, option-list patterns, name and phrase repetition, tier and outcome distributions across many runs, intended-versus-applied severity.
- **Judged checks** for the rest, by a reviewing model or by reading transcripts. Judge output is a screen, not ground truth.
- **Replay.** The event log plus recorded dice let one scenario run again under a different model, prompt or director (see [core engine](../architecture/core-engine.md)). This is also how directors are compared (see [story/02](../story/02-structure-and-direction.md)).

## First uses

- **[Proposed]** Compare the local Ollama model with an API model, by task and by failure mode (see [story/06](../story/06-llm-failure-modes.md#the-local-model-option)). **[Open]** Local output quality is untested.
- **[Proposed]** Measure tier and outcome distributions to check the yes-machine brake and number anchoring.
- **[Proposed]** Compare the null director with a first real director once one exists.

## Open

- **[Open]** Who or what judges the judged checks, and what that costs.
- **[Open]** Where scenarios and recorded runs are stored, and whether they live in the repo.
- **[Open]** Which metrics gate a change (for example, a schema failure rate) and which only inform.
- **[Open]** Whether this is a separate tool or a mode of the engine itself.

## Blind model comparison (built)

`python -m aimaginarium.compare <provider:model> ... [--runs N] [--scenario opening|action|check_outcome] [--variant NAME]` runs the demo world's opening, a plain action and a check outcome through each model with the real prompt library, one call at a time. It writes `blind.md` (replies shuffled and labelled A, B, C per scenario and run), `key.json` (labels back to models) and `metrics.json` (strict schema validity, paragraph count, time to first token, latency, tokens, cached tokens, errors). Judge the prose in `blind.md` first; `--reveal` prints the per-model summary table. It uses the same prompt variants as the game, so it also compares prompt variants on one model by running it with `--variant`.

