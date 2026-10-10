"""Live test script matching the codebase structure for the Z.AI provider."""

import argparse
import asyncio
import os
from dotenv import load_dotenv

from aimaginarium.llm import factory_from_file, StructuredCaller
from aimaginarium.llm.providers.zai import ZAIProvider
from aimaginarium.prompts import PromptBuilder
from aimaginarium.engine import PLAYER_ID, TurnReply, create_demo_world, render_state
from aimaginarium.world import WorldStore


async def main() -> None:
    parser = argparse.ArgumentParser(description="Test Z.AI live provider")
    parser.add_argument("--raw", action="store_true", help="Call provider.generate directly and print raw response text")
    parser.add_argument("--no-thinking", action="store_true", help="Disable thinking mode by passing extra_body={thinking: {type: disabled}}")
    args = parser.parse_args()

    load_dotenv()
    factory = factory_from_file()
    route = factory.route("narrate")

    provider = route.provider
    if args.no_thinking:
        print("Disabling thinking mode via extra_body...")
        api_key = os.environ.get("ZAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        provider = ZAIProvider(
            default_model=route.model,
            api_key=api_key,
            config={"extra_body": {"thinking": {"type": "disabled"}}}
        )

    store = WorldStore.open()
    create_demo_world(store)
    state = render_state(store, PLAYER_ID)

    builder = PromptBuilder.from_directory()
    prompt = builder.build("narrate", state=state)

    schema = prompt.plan.reply_model(TurnReply)
    request = prompt.request(user_text="I ask Marta about the rumors.", schema=schema, model=route.model)

    print(f"Testing model: {route.model}")

    if args.raw:
        print("Calling provider.generate directly (raw output)...")
        try:
            response = await provider.generate(request)
            print("\nRAW RESPONSE TEXT:")
            print(response.text)
        except Exception as exc:
            print("\nRAW GENERATE FAILED:", type(exc), exc)
    else:
        caller = StructuredCaller(provider)
        try:
            validated_obj, response = await caller.call(request, TurnReply)
            print("\nSUCCESS!")
            print("Validated Data:", validated_obj)
            print("Raw Response Text:", response.text)
        except Exception as exc:
            print("\nSTRUCTURED CALL FAILED:", type(exc), exc)


if __name__ == "__main__":
    asyncio.run(main())
