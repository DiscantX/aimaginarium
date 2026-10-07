"""Live probe for the open provider questions.

Run: python local_llm/sample/probe_llm.py ollama [model]
     python local_llm/sample/probe_llm.py gemini <model> 500   (key in .env or the environment)

The last argument sets the cache test's prefix size (about 12 tokens per unit). Gemini's
implicit cache needs roughly 4,096+ tokens, so use 500 there.

Checks (1) whether a full JSON schema, with a nested model and a free-form dict,
is accepted; (2) whether paragraph breaks appear when the narration is one string versus a
list of paragraphs; (3) whether the server reports cached prompt tokens on a repeat call.
"""

import asyncio
import sys
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from aimaginarium.llm import Message, NarrationExtractor, Request, StructuredCaller
from aimaginarium.llm.base import Response
from aimaginarium.llm import LLMProvider, RetryingProvider


class Item(BaseModel):
    name: str
    data: dict[str, Any] = {}


class Turn(BaseModel):
    narration: str
    items: list[Item] = []


class ParagraphTurn(BaseModel):
    narration: list[str] = Field(min_length=2)
    items: list[Item] = []


def build(provider: str, model: str) -> LLMProvider:
    """Builds the provider under test; imports are lazy so only the chosen SDK is needed."""
    if provider == "gemini":
        from aimaginarium.llm.providers.gemini import GeminiProvider
        inner = GeminiProvider(model)
    else:
        from aimaginarium.llm.providers.ollama import OllamaProvider
        inner = OllamaProvider(model, options={"num_ctx": 8192, "num_thread": 2})
    return RetryingProvider(inner, on_retry=lambda n: print(f"   busy ({n.error}); retrying in {n.delay:.0f}s"))


async def main(provider: str, model: str, repeats: int) -> None:
    llm = build(provider, model)
    user = Message("user", "I light a torch and step into the cave.")

    print("1. Full schema (nested model + dict field)")
    system = "You are a game master. Narrate in exactly three paragraphs, then list any items found."
    try:
        turn, response = await StructuredCaller(llm).call(Request(system=system, messages=(user,)), Turn)
        print(f"   accepted; {len(turn.items)} items; usage {response.usage}")
    except Exception as exc:  # noqa: BLE001 - report whatever the server says
        print(f"   FAILED: {exc}")

    print("2. Paragraph breaks: one string versus a list of paragraphs")
    request = Request(system=system, messages=(user,), schema=Turn)
    events = [e async for e in llm.stream(request)]
    raw = next(e for e in events if isinstance(e, Response))
    narration = NarrationExtractor()
    text = narration.feed(raw.text)
    print(f"   string: {text.count(chr(10) * 2)} breaks, {raw.usage.output_tokens} output tokens")
    print(f"   raw reply starts: {raw.text[:160]!r}")
    try:
        turn, response = await StructuredCaller(llm).call(Request(system=system, messages=(user,)), ParagraphTurn)
        print(f"   list: {len(turn.narration)} paragraphs, {response.usage.output_tokens} output tokens")
    except Exception as exc:  # noqa: BLE001
        print(f"   list FAILED: {exc}")

    print(f"3. Prompt cache on a repeated long prefix (about {repeats * 12} tokens)")
    long_system = system + "\n" + "The cave has many chambers and old marks on the walls. " * repeats
    for attempt in (1, 2):
        events = [e async for e in llm.stream(Request(system=long_system, messages=(user,)))]
        usage = next(e for e in events if isinstance(e, Response)).usage
        print(f"   call {attempt}: prompt={usage.prompt_tokens} cached={usage.cached_tokens} output={usage.output_tokens} latency={usage.latency:.1f}s")
    if hasattr(llm, "aclose"):
        await llm.aclose()


load_dotenv()  # finds a .env file in this folder or any parent (the repo root)
asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "phi4-mini", int(sys.argv[3]) if len(sys.argv) > 3 else 120))
