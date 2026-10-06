"""Live probe for the open Ollama questions. Run: python local_llm/tests/probe_ollama.py [model]

Checks (1) whether a full JSON schema, with a nested model and a free-form dict,
is accepted; (2) whether paragraph breaks survive as escaped newlines inside the
narration; (3) whether the server reports cached prompt tokens on a repeat call.
"""

import asyncio
import sys
from typing import Any

from pydantic import BaseModel

from aimaginarium.llm import Message, Request, StructuredCaller, narration_events
from aimaginarium.llm.base import Chunk, Response
from aimaginarium.llm.providers.ollama import OllamaProvider


class Item(BaseModel):
    name: str
    data: dict[str, Any] = {}


class Turn(BaseModel):
    narration: str
    items: list[Item] = []


async def main(model: str) -> None:
    ollama = OllamaProvider(model, num_ctx=8192)
    user = Message("user", "I light a torch and step into the cave.")

    print("1. Full schema (nested model + dict field)")
    system = "You are a game master. Narrate in exactly three paragraphs, then list any items found."
    try:
        turn, response = await StructuredCaller(ollama).call(Request(system=system, messages=(user,)), Turn)
        print(f"   accepted; {len(turn.items)} items; usage {response.usage}")
    except Exception as exc:  # noqa: BLE001 - report whatever the server says
        print(f"   FAILED: {exc}")

    print("2. Paragraph breaks through the streaming extractor")
    request = Request(system=system, messages=(user,), schema=Turn)
    text = "".join([e.text async for e in narration_events(ollama.stream(request)) if isinstance(e, Chunk)])
    print(f"   {text.count(chr(10) * 2)} paragraph breaks in {len(text)} characters")

    print("3. Prompt cache on a repeated long prefix")
    long_system = system + "\n" + "The cave has many chambers and old marks on the walls. " * 120
    for attempt in (1, 2):
        events = [e async for e in ollama.stream(Request(system=long_system, messages=(user,)))]
        usage = next(e for e in events if isinstance(e, Response)).usage
        print(f"   call {attempt}: prompt={usage.prompt_tokens} cached={usage.cached_tokens} latency={usage.latency:.1f}s")
    await ollama.aclose()


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "phi4-mini"))
