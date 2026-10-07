"""Tests for incremental narration extraction."""

import asyncio
import json

import pytest

from aimaginarium.llm import NarrationExtractor, Request, narration_events
from aimaginarium.llm.base import Chunk, Response
from aimaginarium.llm.providers.fake import FakeProvider


def extract(raw: str, size: int) -> str:
    extractor = NarrationExtractor()
    return "".join(extractor.feed(raw[i:i + size]) for i in range(0, len(raw), size))


def reply(narration: str) -> str:
    return json.dumps({"narration": narration, "changes": [{"op": "record", "kind": "x"}]})


@pytest.mark.parametrize("size", [1, 2, 3, 7, 1000])
def test_extracts_narration_at_any_chunk_size(size):
    text = 'She said "run".\n\nBackslash \\ and tab\t done. Caf\u00e9 \U0001F600 ok.'
    assert extract(reply(text), size) == text


def test_stops_at_closing_quote_and_ignores_later_fields():
    raw = '{"narration": "Hello.", "changes": [], "note": "narration"}'
    assert extract(raw, 4) == "Hello."


def test_tolerates_whitespace_and_literal_newlines():
    raw = '{\n  "narration"  :  "One.\nTwo.",\n  "changes": []}'
    assert extract(raw, 5) == "One.\nTwo."


def test_lone_surrogate_becomes_replacement_character():
    assert extract('{"narration": "a\\ud83dz"}', 3) == "a\ufffdz"


def test_no_narration_key_yields_nothing():
    assert extract('{"changes": []}', 3) == ""


def test_done_flag():
    extractor = NarrationExtractor()
    extractor.feed('{"narration": "Hi')
    assert not extractor.done
    extractor.feed('."}')
    assert extractor.done


def test_narration_events_streams_text_then_passes_response_through():
    async def go():
        provider = FakeProvider([reply("First.\n\nSecond.")], chunk_size=6)
        return [e async for e in narration_events(provider.stream(Request()))]

    events = asyncio.run(go())
    assert "".join(e.text for e in events if isinstance(e, Chunk)) == "First.\n\nSecond."
    assert isinstance(events[-1], Response) and events[-1].text.startswith("{")


def list_reply(*paragraphs: str) -> str:
    return json.dumps({"narration": list(paragraphs), "items": []}, indent=2)


@pytest.mark.parametrize("size", [1, 2, 3, 7, 1000])
def test_list_of_paragraphs_is_joined_with_blank_lines(size):
    raw = list_reply("First \u00e9.", 'Second "quoted".', "Third.")
    assert extract(raw, size) == 'First \u00e9.\n\nSecond "quoted".\n\nThird.'


def test_list_stops_at_closing_bracket_and_ignores_later_fields():
    raw = '{"narration": ["One.", "Two."], "note": ["Three."]}'
    assert extract(raw, 3) == "One.\n\nTwo."


def test_list_with_a_single_paragraph_has_no_separator():
    assert extract('{"narration": ["Only."]}', 2) == "Only."


def test_list_streams_incrementally():
    extractor = NarrationExtractor()
    assert extractor.feed('{"narration": ["Hel') == "Hel"
    assert extractor.feed('lo.", "Wor') == "lo.\n\nWor"
    assert not extractor.done
    assert extractor.feed('ld."]}') == "ld." and extractor.done
