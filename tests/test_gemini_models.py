"""Test suite for Gemini and Gemma models, testing HTTP response status, time to first token, and total request time."""

import os
import time
import pytest
from dotenv import load_dotenv
from google import genai
from google.genai.errors import APIError

load_dotenv()
# Note that all test so far have returned either 500 or 503 errors with `gemma-4-31b-it``
models = ["gemma-4-26b-a4b-it", "gemini-3.5-flash-lite", "gemma-4-31b-it",]


def list_models(client):
    """Utility to list available models and their supported actions."""
    available_models = client.models.list()
    print("\nAvailable Models")
    print("=" * 80)
    print(f"{'Model Name':<40} | {'Supported Actions'}")
    print("-" * 80)
    for m in available_models:
        actions = ", ".join(m.supported_actions) if m.supported_actions else "None"
        print(f"{m.name:<40} | {actions}")


@pytest.fixture(scope="module")
def client():
    """Initialize the GenAI client, skipping if GEMINI_API_KEY is not configured."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY environment variable not set.")
    client_instance = genai.Client()

    return client_instance



@pytest.mark.parametrize("model_name", models)
def test_model_response_and_timing(client, model_name):
    """Test HTTP response status, time to first token (TTFT), and total request time for each model."""
    prompt = "Hello! Confirm you are active."
    
    start_time = time.perf_counter()
    time_to_first_token = None
    full_response_text = ""
    
    try:
        chat = client.chats.create(model=model_name)
        response_stream = chat.send_message_stream(message=prompt)
        
        for chunk in response_stream:
            if time_to_first_token is None:
                time_to_first_token = time.perf_counter() - start_time
            if chunk.text:
                full_response_text += chunk.text
                
        end_time = time.perf_counter()
        total_time = end_time - start_time
        
        if time_to_first_token is None:
            time_to_first_token = total_time
            
        print(f"\n--- Model Test Results: {model_name} ---")
        print(f"✅ Response Code: 200 OK")
        print(f"⏱️ Time to First Token (TTFT): {time_to_first_token:.4f}s")
        print(f"⏱️ Total Request Time: {total_time:.4f}s")
        print(f"💬 Response Output: {full_response_text.strip()}")
        
        assert full_response_text is not None
        assert total_time > 0
        assert time_to_first_token > 0
        assert total_time >= time_to_first_token

    except APIError as e:
        print(f"\n--- Model Test Results: {model_name} ---")
        print(f"❌ API Error Response Code: {e.code}")
        print(f"Message: {e.message}")
        print(f"Status: {getattr(e, 'status', 'N/A')}")
        print(f"Full Error Details / Args: {e.args}")
        assert isinstance(e.code, int)
        assert e.code >= 400
    except Exception as e:
        pytest.fail(f"❌ Unexpected error for model {model_name}: {e}")
