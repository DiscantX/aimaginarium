"""Isolates the terminal cursor bug (input overwriting an earlier line).

Run each combination in the terminal where the bug shows, type a few words at
each ``>`` prompt (try long lines that wrap, and pressing Enter while text is
still streaming), and note which combinations garble the screen:

    python scripts/terminal_probe.py --input main --stream newline
    python scripts/terminal_probe.py --input thread --stream newline
    python scripts/terminal_probe.py --input thread --stream none
    python scripts/terminal_probe.py --input thread --stream none --wrap

The game itself is ``--input thread --stream none``: narration arrives in small
pieces without line breaks, and the prompt is read in a worker thread.
"""

import argparse
import asyncio
import shutil
import textwrap
import time

TEXT = ("The fire crackles softly, casting long, flickering shadows against the low wooden beams of the taproom. "
        "Marta extinguishes the wall sconces one by one, leaving the room lit only by the dying embers of the hearth. ")


async def stream(mode: str, wrap: bool) -> None:
    text = TEXT * 3
    if wrap:
        text = textwrap.fill(text, width=shutil.get_terminal_size().columns, break_long_words=False)
    for i in range(0, len(text), 6):
        print(text[i:i + 6], end="", flush=True)
        await asyncio.sleep(0.02)
    print("\n" if mode == "newline" else "", end="", flush=True)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", choices=["main", "thread"], default="thread")
    parser.add_argument("--stream", choices=["newline", "none"], default="none")
    parser.add_argument("--wrap", action="store_true", help="wrap the streamed text to the terminal width first")
    args = parser.parse_args()
    for turn in range(4):
        await stream(args.stream, args.wrap)
        if args.stream == "none":
            print()
        if args.input == "thread":
            reply = await asyncio.to_thread(input, "> ")
        else:
            reply = input("> ")
        print(f"(you typed {len(reply)} characters)")
        time.sleep(0.1)


asyncio.run(main())
