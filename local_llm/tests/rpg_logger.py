import os
import json
import time
from datetime import datetime

class RPGLogger:
    """
    A modular, reusable session logger for local LLM engines.
    Creates a unique timestamped file per session and records configuration metrics,
    execution latency performance, and verbose transaction prompts.
    """
    def __init__(self, log_dir="logs", verbose=False):
        self.log_dir = log_dir
        self.verbose = verbose
        
        # Ensure log directory exists
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
            
        # Create unique filename based on current session timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_filepath = os.path.join(self.log_dir, f"session_{timestamp}.log")
        
        # Initialize an empty log file with standard header structure
        self._write_entry("=== GAME RPG ENGINE RUNTIME LOG initialized ===")

    def _write_entry(self, message: str):
        """Append a clean text entry with a local timestamp to the file."""
        time_str = datetime.now().strftime("%H:%M:%S")
        with open(self.log_filepath, "a", encoding="utf-8") as f:
            f.write(f"[{time_str}] {message}\n")

    def log_settings(self, model_name: str, num_ctx: int, temperature: float, num_thread: int):
        """Record the active generation options fed to Ollama."""
        self._write_entry("--- SYSTEM HARDWARE SETTINGS ---")
        self._write_entry(f"Model Name:      {model_name}")
        self._write_entry(f"Context Limit:   {num_ctx} tokens")
        self._write_entry(f"Temperature:     {temperature}")
        self._write_entry(f"Worker Threads:  {num_thread if num_thread else 'Default / Auto'}")
        self._write_entry("--------------------------------\n")

    def log_preload_time(self, seconds: float):
        """Record how long the cold-start model weight caching took."""
        self._write_entry(f"⚡ Model Preload Completed in: {seconds:.3f} seconds\n")

    def log_turn(self, player_input: str, system_prompt: str, output_text: str, 
                 time_to_first_token: float, total_generation_time: float):
        """
        Calculates approximate feed size and records raw latency metrics 
        for an individual action evaluation.
        """
        # Rule of thumb calculation: 1 word ~ 0.75 tokens -> Words / 0.75
        approx_prompt_words = len((system_prompt + player_input).split())
        approx_prompt_tokens = int(approx_prompt_words / 0.75)

        self._write_entry("--- ACTION TRANSACTION TURN ---")
        self._write_entry(f"⏱️ Time to First Token:  {time_to_first_token:.3f}s")
        self._write_entry(f"⏱️ Total Response Time: {total_generation_time:.3f}s")
        self._write_entry(f"📊 Approximate Input Context Fed: {approx_prompt_tokens} tokens")
        
        if self.verbose:
            self._write_entry(f"📥 Player Action Sent: \"{player_input.strip()}\"")
            # Log structured text clean without json structure pollution
            clean_output = output_text.strip().replace("\n", " ")
            self._write_entry(f"📤 Engine Reply Text:  \"{clean_output}\"")
            
        self._write_entry("-------------------------------\n")
