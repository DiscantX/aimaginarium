import os
import pytest
from local_llm.sample.rpg_logger import RPGLogger

def test_rpg_logger_actual_tokens(tmp_path):
    log_dir = tmp_path / "logs"
    logger = RPGLogger(log_dir=str(log_dir), verbose=True)
    logger.log_settings("test-model", 4096, 0.7, 2)
    logger.log_turn(
        player_input="look around",
        system_prompt="You are a GM.",
        output_text="You see a room.",
        time_to_first_token=0.5,
        total_generation_time=1.5,
        conversation_history=[{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}],
        actual_tokens=150
    )
    
    log_files = list(log_dir.glob("session_*.log"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")
    assert "Input Context Fed (Actual): 150 tokens" in content

def test_rpg_logger_approximate_true_prompt(tmp_path):
    log_dir = tmp_path / "logs"
    logger = RPGLogger(log_dir=str(log_dir), verbose=False)
    logger.log_turn(
        player_input="open door",
        system_prompt="System prompt text here.",
        output_text="The door is locked.",
        time_to_first_token=0.4,
        total_generation_time=1.0,
        conversation_history=[{"role": "user", "content": "hello world"}, {"role": "assistant", "content": "greetings traveler"}],
        actual_tokens=None
    )
    
    log_files = list(log_dir.glob("session_*.log"))
    assert len(log_files) == 1
    content = log_files[0].read_text(encoding="utf-8")
    assert "Approximate Input Context Fed (True Prompt)" in content
