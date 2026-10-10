"""Blind comparison of models on the same prompts.

Runs scenarios from the demo world through the real prompt library and each
candidate model, then writes the replies shuffled and unlabelled (``blind.md``)
so they can be judged without knowing the model, plus ``key.json`` and
``metrics.json``. Read ``blind.md`` before opening the others.

    python -m aimaginarium.compare gemini:gemini-3.5-flash-lite gemini:gemma-4-31b-it --runs 2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence

from dotenv import load_dotenv
from pydantic import ValidationError

from .engine import OutcomeReply, PLAYER_ID, TurnReply, create_demo_world, render_state
from .engine.rules import D20Rules
from .llm import Candidate, Message, ProviderError, ProviderFactory, Response, Route, factory_from_file
from .llm.structured import strip_fences
from .prompts import PromptBuilder
from .world import WorldStore

SCENARIOS = ("opening", "action", "check_outcome")


@dataclass(frozen=True)
class Result:
    """One model's answer to one scenario run.

    Attributes:
        scenario: Which scenario.
        run: Run number, from 1.
        model: The ``provider:model`` label.
        text: The narration, or empty if the reply could not be read.
        valid: Whether the reply matched the schema exactly (paragraph count included).
        paragraphs: Paragraphs in the narration.
        error: Why the call or the reading failed, if it did.
        ttft: Seconds to first token.
        latency: Seconds for the whole reply.
        prompt_tokens: Tokens in the prompt.
        cached_tokens: Prompt tokens served from cache, if reported.
        output_tokens: Tokens generated.
    """

    scenario: str
    run: int
    model: str
    text: str = ""
    valid: bool = False
    paragraphs: int = 0
    error: str = ""
    ttft: Optional[float] = None
    latency: float = 0.0
    prompt_tokens: int = 0
    cached_tokens: Optional[int] = None
    output_tokens: int = 0


def build_request(builder: PromptBuilder, store: WorldStore, scenario: str, variant: Optional[str] = None):
    """Builds the request for a scenario from the demo world.

    Args:
        builder: The prompt library.
        store: A world made by :func:`create_demo_world`.
        scenario: One of :data:`SCENARIOS`.
        variant: A recipe variant to force.

    Returns:
        The request, ready to send.
    """
    print("Build request...")
    state = render_state(store, PLAYER_ID)
    if scenario == "opening":
        return builder.build("opening", state=state, variant=variant).request(schema=TurnReply)
    if scenario == "action":
        prompt = builder.build("narrate", state=state, variant=variant)
        return prompt.request(user_text="I ask Marta what the regulars have been whispering about.", schema=TurnReply)
    if scenario == "check_outcome":
        roll = D20Rules(random.Random(0)).roll(store.get_entity(PLAYER_ID), "stealth", 12)
        values = {"roll": roll.die, "skill": roll.skill, "difficulty": roll.difficulty, "margin": roll.margin,
                  "classification": "failure", "tier": "easy"}
        prompt = builder.build("check_outcome", state={**state, **values}, variant=variant)
        before = [("user", "I try to slip the key off its nail behind the bar while Marta's back is turned."),
                  ("assistant", "You wait until Marta bends to a cask, then reach over the bar for the key.")]
        return prompt.request([Message(r, c) for r, c in before], schema=OutcomeReply)
    raise ValueError(f"unknown scenario {scenario!r}")


async def run_one(candidate: Candidate, request, scenario: str, run: int) -> Result:
    """Sends one request to one candidate and scores the reply."""
    print("Run one...")
    label = candidate.label
    started = time.monotonic()
    final: Optional[Response] = None
    try:
        async for event in Route([candidate], scenario).stream(request):
            if isinstance(event, Response):
                final = event
    except ProviderError as exc:
        return Result(scenario, run, label, error=f"{type(exc).__name__}: {exc}", latency=time.monotonic() - started)
    usage = final.usage
    base = dict(scenario=scenario, run=run, model=label, ttft=usage.time_to_first_token, latency=usage.latency,
                prompt_tokens=usage.prompt_tokens, cached_tokens=usage.cached_tokens, output_tokens=usage.output_tokens)
    try:
        data = json.loads(strip_fences(final.text))
        parts = data["narration"]
        paragraphs = parts if isinstance(parts, list) else [str(parts)]
    except (ValueError, KeyError, TypeError) as exc:
        return Result(**base, error=f"unreadable reply: {exc}")
    try:
        request.schema.model_validate(data)
        valid, error = True, ""
    except ValidationError as exc:
        valid, error = False, f"schema: {exc.errors()[0]['msg']}"
    return Result(**base, text="\n\n".join(paragraphs), valid=valid, paragraphs=len(paragraphs), error=error)


async def compare(
    factory: ProviderFactory, specs: Sequence[str], scenarios: Sequence[str] = SCENARIOS, runs: int = 1,
    variant: Optional[str] = None, builder: Optional[PromptBuilder] = None,
) -> list[Result]:
    """Runs every scenario on every model, one call at a time (gentle on free-tier limits).

    Args:
        factory: Source of providers.
        specs: ``provider:model`` labels to compare.
        scenarios: Which scenarios to run.
        runs: Calls per model and scenario.
        variant: A recipe variant to force.
        builder: The prompt library; defaults to the shipped one.

    Returns:
        One result per call, in order.
    """
    print("Compare...")
    builder = builder or PromptBuilder.from_directory()
    candidates = [factory.candidate(spec) for spec in specs]
    results = []
    with WorldStore.open() as store:
        create_demo_world(store)
        for scenario in scenarios:
            request = build_request(builder, store, scenario, variant)
            for run in range(1, runs + 1):
                for candidate in candidates:
                    results.append(await run_one(candidate, request, scenario, run))
    return results


def write_report(results: Sequence[Result], out: Path, seed: Optional[int] = None) -> None:
    """Writes the blind file, the key and the metrics.

    Args:
        results: What :func:`compare` returned.
        out: Directory to write into (created).
        seed: Seed for the shuffle, for reproducibility.
    """
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    key: dict[str, str] = {}
    lines = ["# Blind comparison", "", "Judge the prose, then open key.json.", ""]
    groups: dict[tuple[str, int], list[Result]] = {}
    for result in results:
        groups.setdefault((result.scenario, result.run), []).append(result)
    for (scenario, run), group in groups.items():
        shuffled = rng.sample(group, len(group))
        lines += [f"## {scenario}, run {run}", ""]
        for letter, result in zip("ABCDEFGHIJ", shuffled):
            key[f"{scenario}/{run}/{letter}"] = result.model
            lines += [f"### {letter}", "", result.text or f"*(no usable reply)*", ""]
    (out / "blind.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "key.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
    (out / "metrics.json").write_text(json.dumps([asdict(r) for r in results], indent=2), encoding="utf-8")


def summary(results: Sequence[Result]) -> str:
    """Returns a per-model table of validity, speed and tokens (reveals the models)."""
    rows = {}
    for r in results:
        rows.setdefault(r.model, []).append(r)
    out = [f"{'model':42} {'valid':>7} {'ttft':>6} {'total':>6} {'out tok':>8}  errors"]
    for model, rs in rows.items():
        ttfts = [r.ttft for r in rs if r.ttft is not None]
        out.append(f"{model:42} {sum(r.valid for r in rs):>3}/{len(rs):<3} "
                   f"{(sum(ttfts) / len(ttfts) if ttfts else float('nan')):>6.2f} "
                   f"{sum(r.latency for r in rs) / len(rs):>6.2f} {sum(r.output_tokens for r in rs) / len(rs):>8.0f}  "
                   f"{sum(1 for r in rs if r.error)}")
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point for ``python -m aimaginarium.compare``."""
    parser = argparse.ArgumentParser(description="Blind comparison of models on the same prompts.")
    parser.add_argument("models", nargs="+", help="provider:model labels, as in the configuration")
    parser.add_argument("--config")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--scenario", action="append", choices=SCENARIOS, help="default: all")
    parser.add_argument("--variant", help="force a recipe variant")
    parser.add_argument("--out", default="compare_out")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--reveal", action="store_true", help="print the summary table (names the models)")
    args = parser.parse_args(argv)
    load_dotenv()
    results = asyncio.run(compare(factory_from_file(args.config), args.models, args.scenario or SCENARIOS,
                                  args.runs, args.variant))
    out = Path(args.out) / time.strftime("%Y%m%d-%H%M%S")
    write_report(results, out, args.seed)
    print(f"Wrote {out}. Read blind.md first, then key.json and metrics.json.")
    if args.reveal:
        print(summary(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
