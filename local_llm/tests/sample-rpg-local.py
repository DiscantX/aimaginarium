import json
import ollama
import sys
import time
import threading
import random

# 1. Initialize your strict state variables in Python
game_state = {
    "player_name": "Valen",
    "hp": 100,
    "gold": 20,
    "inventory": ["rusty dagger", "health potion"],
    "current_location": "The Dusty Tavern"
}

class RPGNarrativeLoader:
    """
    A modular, reusable context manager that handles a live-spinning loader 
    with cycling playful messages in a background thread.
    """
    def __init__(self):
        self.spin_symbols = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.playful_messages = [
            "Consulting the dark oracle...",
            "Rolling hidden 20-sided dice...",
            "Summoning aggressive goblins...",
            "Stoking the tavern fireplace...",
            "Polishing rusty daggers...",
            "Weaving threads of fate...",
            "Brewing terrible potions...",
            "Bribing the local town guards..."
        ]
        self._stop_event = threading.Event()
        self._thread = None

    def _animate(self):
        msg = random.choice(self.playful_messages)
        symbol_idx = 0
        last_msg_change = time.time()
        
        while not self._stop_event.is_set():
            if time.time() - last_msg_change > 2.5:
                msg = random.choice(self.playful_messages)
                last_msg_change = time.time()
                
            symbol = self.spin_symbols[symbol_idx % len(self.spin_symbols)]
            sys.stdout.write(f"\r\033[K \033[35m{symbol}\033[0m {msg}")
            sys.stdout.flush()
            
            symbol_idx += 1
            time.sleep(0.08)

    def __enter__(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def stop(self):
        """Explicitly stops the animation thread and clears the terminal line."""
        if not self._stop_event.is_set():
            self._stop_event.set()
            if self._thread:
                self._thread.join()
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()


def preload_model(model_name="phi4-mini"):
    print(f"🔄 Preloading model '{model_name}' into memory... Please wait.", end="", flush=True)
    ollama.generate(model=model_name, prompt="", options={"num_ctx": 2048})
    print("\r✨ Model preloaded successfully! Ready to play.                 \n")


def get_llm_turn_and_stream(player_action):
    system_prompt = (
        "You are the Game Master of a grim text RPG. Your job is to resolve the player's action.\n"
        "You must evaluate if the action succeeds, write a descriptive atmosphere, and return stat modifiers.\n\n"
        
        "CRITICAL STORYTELLING REQUIREMENT:\n"
        "The 'narrative' text value MUST be a fully fleshed out, deep, and atmospheric story. "
        "It must consist of EXACTLY 3 distinct, long paragraphs separated by newline characters (\\n\\n). "
        "Do not summarize or cut the description short.\n\n"
        
        f"CURRENT WORLD STATE:\n{json.dumps(game_state, indent=2)}\n\n"
        "CRITICAL: You must reply ONLY with a single valid JSON object matching this exact schema:\n"
        "{\n"
        '  "narrative": "Your deep 3-paragraph story goes here...",\n'
        '  "hp_modifier": -10 or 20 or 0,\n'
        '  "gold_modifier": -5 or 15 or 0,\n'
        '  "item_discovered": "item_name" or null,\n'
        '  "item_lost": "item_name" or null,\n'
        '  "new_location": "Name of new area" or null\n'
        "}"
    )


    loader = RPGNarrativeLoader()
    full_text = ""
    narrative_buffer = ""
    inside_narrative = False
    escaped = False
    
    # Start the loading animation
    with loader:
        response_stream = ollama.chat(
            model="phi4-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"The player attempts to: {player_action}"}
            ],
            format="json", 
            stream=True,
            options={
                "temperature": 0.9,
                "num_ctx": 16384, #12288 #2048 or 4096 for faster responses. 12288 works but is slow.
                "num_thread": 2 # 🧵 Restricts Ollama to exactly 3 CPU threads
            }
        )
        
        # Convert response_stream iterator into an explicit reference we can advance manually
        stream_iterator = iter(response_stream)
        
        try:
            # 1. Pull the absolute FIRST token while STILL INSIDE the 'with loader' context block.
            # This causes Python to block here while the spinner continues to animate.
            first_chunk = next(stream_iterator)
            first_token = first_chunk['message']['content']
            full_text += first_token
        except StopIteration:
            # Handle rare immediate empty streams gracefully
            first_token = ""

    # The context manager exits naturally here, killing the background thread
    # and sweeping the loader line clean before printing anything to the player.

    # 2. Process that first chunk now that the screen is clean
    if first_token:
        if '"narrative":' in full_text:
            idx = full_text.find('"narrative":') + 12
            while idx < len(full_text) and full_text[idx] in [' ', '\n', '\r', '\t']:
                idx += 1
            if idx < len(full_text) and full_text[idx] == '"':
                inside_narrative = True
                remainder = full_text[idx+1:]
                sys.stdout.write(remainder)
                sys.stdout.flush()
            narrative_buffer = full_text

    # 3. Stream all subsequent tokens normally
    for chunk in stream_iterator:
        token = chunk['message']['content']
        full_text += token
        
        if not inside_narrative:
            if '"narrative":' in full_text and '"narrative": "' not in narrative_buffer:
                idx = full_text.find('"narrative":') + 12
                while idx < len(full_text) and full_text[idx] in [' ', '\n', '\r', '\t']:
                    idx += 1
                if idx < len(full_text) and full_text[idx] == '"':
                    inside_narrative = True
                    remainder = full_text[idx+1:]
                    sys.stdout.write(remainder)
                    sys.stdout.flush()
                narrative_buffer = full_text
        else:
            for char in token:
                if escaped:
                    sys.stdout.write(char)
                    sys.stdout.flush()
                    escaped = False
                elif char == '\\':
                    sys.stdout.write(char)
                    sys.stdout.flush()
                    escaped = True
                elif char == '"':
                    inside_narrative = False
                    break
                else:
                    sys.stdout.write(char)
                    sys.stdout.flush()
                        
    print("\n----------------------------------------")
    return json.loads(full_text)


# --- MAIN GAME LOOP ---
preload_model("phi4-mini")

print(f"=== Welcome to the AI RPG, {game_state['player_name']}! ===")
print(f"You begin your journey in: {game_state['current_location']}\n")

while game_state["hp"] > 0:
    action = input("\nWhat do you want to do? > ")
    if action.lower() in ["quit", "exit"]:
        break
        
    try:
        result = get_llm_turn_and_stream(action)
        
        # Update Python state based on LLM decision
        game_state["hp"] += result.get("hp_modifier", 0)
        game_state["gold"] += result.get("gold_modifier", 0)
        
        if result.get("item_discovered"):
            game_state["inventory"].append(result["item_discovered"])
        if result.get("item_lost") in game_state["inventory"]:
            game_state["inventory"].remove(result["item_lost"])
        if result.get("new_location"):
            game_state["current_location"] = result["new_location"]
            
        # Present modern stats block back to the user
        print(f"❤️ HP: {game_state['hp']} | 💰 Gold: {game_state['gold']} | 📍 Location: {game_state['current_location']}")
        print(f"🎒 Inventory: {', '.join(game_state['inventory'])}")
        
    except Exception as e:
        print("\n[The engine stumbled over an action calculation. Please try another action.]")

print("\nGame Over. Thanks for playing!")
