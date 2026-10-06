import json
import ollama
import sys
import time
from rpg_logger import RPGLogger  # 📥 Import your modular logger

# Game configuration constraints
MODEL_NAME = "phi4-mini"
NUM_CTX = 12288
TEMPERATURE = 0.85
NUM_THREAD = 4
VERBOSE_LOGGING = True  # Toggle this to False if you want to skip dialogue tracking

# 1. Initialize your state and the tracking module
game_state = {
    "player_name": "Valen",
    "hp": 100,
    "gold": 20,
    "inventory": ["rusty dagger", "health potion"],
    "current_location": "The Dusty Tavern"
}

logger = RPGLogger(verbose=VERBOSE_LOGGING)
logger.log_settings(MODEL_NAME, NUM_CTX, TEMPERATURE, NUM_THREAD)

# (Keep your original RPGNarrativeLoader class completely unchanged here)
class RPGNarrativeLoader:
    def __init__(self):
        self.spin_symbols = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.playful_messages = ["Consulting the dark oracle...", "Rolling hidden 20-sided dice..."]
        import threading
        self._stop_event = threading.Event()
        self._thread = None
    def _animate(self):
        import random
        msg = random.choice(self.playful_messages)
        symbol_idx = 0
        while not self._stop_event.is_set():
            symbol = self.spin_symbols[symbol_idx % len(self.spin_symbols)]
            sys.stdout.write(f"\r\033[K \033[35m{symbol}\033[0m {msg}")
            sys.stdout.flush()
            symbol_idx += 1
            time.sleep(0.08)
    def __enter__(self):
        import threading
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()
        return self
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
    def stop(self):
        if not self._stop_event.is_set():
            self._stop_event.set()
            if self._thread:
                self._thread.join()
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()


def preload_model():
    print(f"🔄 Preloading model '{MODEL_NAME}' into memory... Please wait.", end="", flush=True)
    start_preload = time.perf_counter()
    
    ollama.generate(model=MODEL_NAME, prompt="", options={"num_ctx": NUM_CTX, "num_thread": NUM_THREAD})
    
    end_preload = time.perf_counter()
    preload_duration = end_preload - start_preload
    
    print("\r✨ Model preloaded successfully! Ready to play.                 \n")
    logger.log_preload_time(preload_duration) # Log it!


def get_llm_turn_and_stream(player_action):
    system_prompt = (
        "You are the Game Master of a grim text RPG. Your job is to resolve the player's action.\n"
        "You must evaluate if the action succeeds, write a descriptive atmosphere, and return stat modifiers.\n\n"
        "CRITICAL STORYTELLING REQUIREMENT:\n"
        "The 'narrative' text value MUST be a long, deeply descriptive story block consisting of EXACTLY "
        "3 long paragraphs. Because you are inside a JSON string, you must NOT use literal line breaks. "
        "Instead, place the literal marker '[BREAK]' between your paragraphs so the game engine can format them.\n\n"
        f"CURRENT WORLD STATE:\n{json.dumps(game_state, indent=2)}\n\n"
        "CRITICAL: You must reply ONLY with a single valid JSON object matching this exact schema:\n"
        "{\n"
        '  "narrative": "Paragraph one... [BREAK] Paragraph two... [BREAK] Paragraph three...",\n'
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
    
    # --- PERFORMANCE TIMING START ---
    start_call = time.perf_counter()
    first_token_time = 0.0

    with loader:
        response_stream = ollama.chat(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"The player attempts to: {player_action}"}
            ],
            format="json", 
            stream=True,
            options={
                "temperature": TEMPERATURE,
                "num_ctx": NUM_CTX,
                "num_thread": NUM_THREAD
            }
        )
        
        stream_iterator = iter(response_stream)
        
        try:
            first_chunk = next(stream_iterator)
            first_token_time = time.perf_counter() - start_call  # ⏱️ Catch Time To First Token!
            first_token = first_chunk['message']['content']
            full_text += first_token
        except StopIteration:
            first_token = ""

    if first_token:
        if '"narrative":' in full_text:
            idx = full_text.find('"narrative":') + 12
            while idx < len(full_text) and full_text[idx] in [' ', '\n', '\r', '\t']:
                idx += 1
            if idx < len(full_text) and full_text[idx] == '"':
                inside_narrative = True
                remainder = full_text[idx+1:]
                # (Keep remainder buffering strategy identical)
                narrative_buffer = full_text

    stream_buffer = ""
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
                    for c in remainder:
                        if c == '"': inside_narrative = False; break
                        stream_buffer += c
                        if "[BREAK]" in stream_buffer:
                            sys.stdout.write("\n\n")
                            stream_buffer = ""
                        elif not "[BREAK]".startswith(stream_buffer):
                            sys.stdout.write(stream_buffer)
                            stream_buffer = ""
                    sys.stdout.flush()
                narrative_buffer = full_text
        else:
            for char in token:
                if escaped:
                    stream_buffer += char
                    escaped = False
                elif char == '\\':
                    escaped = True
                    continue
                elif char == '"':
                    inside_narrative = False
                    break
                else:
                    stream_buffer += char
                
                if "[BREAK]" in stream_buffer:
                    sys.stdout.write("\n\n")
                    sys.stdout.flush()
                    stream_buffer = ""
                elif stream_buffer and not "[BREAK]".startswith(stream_buffer):
                    sys.stdout.write(stream_buffer)
                    sys.stdout.flush()
                    stream_buffer = ""

    if stream_buffer:
        sys.stdout.write(stream_buffer)
        sys.stdout.flush()
                        
    total_generation_time = time.perf_counter() - start_call  # ⏱️ Catch Total Operational Duration
    print("\n----------------------------------------")
    
    final_data = json.loads(full_text)
    
    # 📝 Log the calculated statistics down into our log tracking class
    logger.log_turn(
        player_input=player_action,
        system_prompt=system_prompt,
        output_text=final_data.get("narrative", ""),
        time_to_first_token=first_token_time,
        total_generation_time=total_generation_time
    )

    if "narrative" in final_data:
        final_data["narrative"] = final_data["narrative"].replace("[BREAK]", "\n\n")
    return final_data

# --- MAIN GAME LOOP RUNNER ---
preload_model()

print(f"=== Welcome to the AI RPG, {game_state['player_name']}! ===")
print(f"You begin your journey in: {game_state['current_location']}\n")

while game_state["hp"] > 0:
    action = input("\nWhat do you want to do? > ")
    if action.lower() in ["quit", "exit"]:
        break
        
    try:
        result = get_llm_turn_and_stream(action)
        
        # State tracking updates
        game_state["hp"] += result.get("hp_modifier", 0)
        game_state["gold"] += result.get("gold_modifier", 0)
        if result.get("item_discovered"):
            game_state["inventory"].append(result["item_discovered"])
        if result.get("item_lost") in game_state["inventory"]:
            game_state["inventory"].remove(result["item_lost"])
        if result.get("new_location"):
            game_state["current_location"] = result["new_location"]
            
        print(f"❤️ HP: {game_state['hp']} | 💰 Gold: {game_state['gold']} | 📍 Location: {game_state['current_location']}")
        print(f"🎒 Inventory: {', '.join(game_state['inventory'])}")
        
    except Exception as e:
        print("\n[The engine stumbled over an action calculation. Please try another action.]")

print("\nGame Over. Thanks for playing!")
