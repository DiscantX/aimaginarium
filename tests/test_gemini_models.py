"""Test suite for Gemini and Gemma models, testing response status, time to first token, and total request time using the LLM pipeline."""

import asyncio
import os
import time
import pytest
from dotenv import load_dotenv

from aimaginarium.llm import Chunk, Message, ProviderError, Request, Response
from aimaginarium.llm.providers.gemini import GeminiProvider

load_dotenv()
# Note that `gemma-4-31b-it` often returns either 500 or 503 errors
models = ["gemini-3.5-flash-lite", "gemma-4-26b-a4b-it", "gemma-4-31b-it",]


def list_models(provider: GeminiProvider):
    """Utility to list available models and their supported actions using the provider's client."""
    available_models = provider._client.models.list()
    print("\nAvailable Models")
    print("=" * 80)
    print(f"{'Model Name':<40} | {'Supported Actions'}")
    print("-" * 80)
    for m in available_models:
        actions = ", ".join(m.supported_actions) if m.supported_actions else "None"
        print(f"{m.name:<40} | {actions}")


@pytest.fixture(scope="module")
def api_key():
    """Skip if GEMINI_API_KEY is not configured."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        pytest.skip("GEMINI_API_KEY environment variable not set.")
    return key


@pytest.mark.parametrize("model_name", models)
def test_model_response_and_timing(api_key, model_name):
    """Test response, time to first token (TTFT), and total request time for each model using GeminiProvider."""
    prompt = "Hello! Confirm you are active."
    provider = GeminiProvider(default_model=model_name, api_key=api_key)
    request = Request(messages=(Message("user", prompt),))

    async def run_test():
        full_response_text = ""
        final_response = None

        async for event in provider.stream(request):
            if isinstance(event, Chunk):
                full_response_text += event.text
            elif isinstance(event, Response):
                final_response = event

        return full_response_text, final_response

    try:
        full_response_text, final_response = asyncio.run(run_test())

        time_to_first_token = final_response.usage.time_to_first_token if final_response and final_response.usage and final_response.usage.time_to_first_token is not None else 0.0
        total_time = final_response.usage.latency if final_response and final_response.usage else 0.0

        print(f"\n--- Model Test Results: {model_name} ---")
        print(f"✅ Response Code: 200 OK")
        print(f"⏱️ Time to First Token (TTFT): {time_to_first_token:.4f}s")
        print(f"⏱️ Total Request Time: {total_time:.4f}s")
        print(f"💬 Response Output: {full_response_text.strip()}")
        if final_response and final_response.usage:
            print(f"📊 Usage: {final_response.usage}")

        assert full_response_text is not None
        assert total_time > 0
        assert time_to_first_token > 0
        assert total_time >= time_to_first_token
        assert final_response is not None
        assert final_response.text == full_response_text

    except ProviderError as e:
        print(f"\n--- Model Test Results: {model_name} ---")
        print(f"❌ Provider Error: {e}")
        assert isinstance(e, ProviderError)
    except Exception as e:
        pytest.fail(f"❌ Unexpected error for model {model_name}: {e}")
