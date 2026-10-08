"""Tests for the prompt library: fragments, recipes, plans, variants and the builder."""

from collections.abc import Mapping

import pytest
from pydantic import BaseModel, ValidationError

from aimaginarium.llm import Message
from aimaginarium.prompts import (
    BASE, FileFragmentSource, Fixed, LIBRARY, NarrationPlan, PerSession, Pinned, PromptBuilder, PromptError, Slot,
    load_recipe,
)
from aimaginarium.prompts.fragments import parse_fragment, substitute

RECIPE = """
id = "demo"
task = "narrate"
system = ["a", "b"]
state = ["scene", "mood/{mood}"]

[[plan]]
id = "world"
count = 2
instruction = "Describe the world."

[[plan]]
id = "scene"
min = 1
max = 3
instruction = "Describe the scene."

[variants.short]
system = ["a"]
"""

FRAGMENTS = {
    "a": "---\ndescription: first\n---\nA says {name}.",
    "b": "B is stable.",
    "scene": "Scene: {where}",
    "mood/happy": "Be cheerful.",
    "mood/sad": "Be gloomy.",
}


@pytest.fixture
def builder(tmp_path):
    for fid, text in FRAGMENTS.items():
        path = tmp_path / "fragments" / f"{fid}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    (tmp_path / "recipes").mkdir()
    (tmp_path / "recipes" / "demo.toml").write_text(RECIPE)
    return PromptBuilder.from_directory(tmp_path)


STATIC, STATE = {"name": "Ada"}, {"where": "a cellar", "mood": "sad"}


def test_front_matter_is_split_from_text_and_braces_without_names_survive():
    fragment = parse_fragment("x", "---\ndescription: hi\nstatus: draft\n---\nUse {\"a\": 1} and {name}.\n")
    assert fragment.meta == {"description": "hi", "status": "draft"}
    assert fragment.render({"name": "Ada"}) == 'Use {"a": 1} and Ada.'


def test_fragment_digest_follows_the_text():
    assert parse_fragment("x", "one").digest != parse_fragment("x", "two").digest
    assert parse_fragment("x", "one").digest == parse_fragment("y", "---\nk: v\n---\none").digest


def test_missing_value_names_the_placeholder():
    with pytest.raises(PromptError, match="no value for who"):
        substitute("hello {who}", {}, "fragment 'x'")


def test_unknown_and_escaping_fragment_ids_are_errors(tmp_path):
    (tmp_path / "ok.md").write_text("x")
    source = FileFragmentSource(tmp_path / "sub")
    (tmp_path / "sub").mkdir()
    with pytest.raises(PromptError, match="unknown fragment"):
        source.get("nope")
    with pytest.raises(PromptError, match="unknown fragment"):
        source.get("../ok")


def test_stable_content_in_system_and_changing_state_last(builder):
    prompt = builder.build("demo", STATIC, STATE)
    assert "A says Ada." in prompt.system and "B is stable." in prompt.system
    assert "cellar" not in prompt.system and "gloomy" not in prompt.system
    request = prompt.request([Message("user", "hi"), Message("assistant", "yo")], "I open the door.")
    assert request.system == prompt.system
    assert [m.role for m in request.messages] == ["user", "assistant", "user"]
    assert request.messages[-1].content == "Scene: a cellar\n\nBe gloomy.\n\nI open the door."


def test_system_prompt_is_identical_when_only_state_changes(builder):
    first = builder.build("demo", STATIC, {"where": "a cellar", "mood": "sad"})
    second = builder.build("demo", STATIC, {"where": "a tower", "mood": "happy"})
    assert first.system == second.system and first.state != second.state


def test_fragment_ids_take_placeholders_from_state(builder):
    assert "cheerful" in builder.build("demo", STATIC, {**STATE, "mood": "happy"}).state
    with pytest.raises(PromptError, match="unknown fragment"):
        builder.build("demo", STATIC, {**STATE, "mood": "angry"})


def test_record_names_recipe_variant_and_fragment_hashes(builder):
    record = builder.build("demo", STATIC, STATE).record()
    assert record["recipe"] == "demo" and record["variant"] == BASE
    assert set(record["fragments"]) == {"a", "b", "scene", "mood/sad"}


def test_variant_replaces_only_what_it_names(builder):
    prompt = builder.build("demo", STATIC, STATE, variant="short")
    assert "B is stable." not in prompt.system and prompt.variant == "short"
    assert "Scene: a cellar" in prompt.state  # state and plan are inherited
    with pytest.raises(PromptError, match="no variant"):
        builder.build("demo", STATIC, STATE, variant="nope")


def test_unknown_recipe_is_an_error(builder):
    with pytest.raises(PromptError, match="unknown recipe"):
        builder.build("nope")


def test_policies(builder):
    recipe = builder.recipe("demo")
    assert Fixed("short").choose(recipe) == "short" and Fixed("missing").choose(recipe) == BASE
    assert Pinned({"demo": "short"}).choose(recipe) == "short" and Pinned({}).choose(recipe) == BASE
    policy = PerSession("s1")
    assert policy.choose(recipe) == PerSession("s1").choose(recipe) in recipe.variants
    assert {PerSession(f"s{i}").choose(recipe) for i in range(30)} == set(recipe.variants)
    assert PromptBuilder.from_directory(builder.recipes_dir.parent, Pinned({"demo": "short"})).build("demo", STATIC, STATE).variant == "short"


def test_plan_describes_slots_and_tags_paragraphs_by_position():
    plan = NarrationPlan([Slot("world", "W", 3), Slot("place", "P", 2), Slot("scene", "S", 1, 3)])
    assert (plan.min, plan.max) == (6, 8)
    assert [plan.slot_of(i).id for i in range(8)] == ["world"] * 3 + ["place"] * 2 + ["scene"] * 3
    text = plan.describe()
    assert "6 to 8 paragraphs" in text and "Paragraphs 1-3 (world): W" in text and "Paragraphs 6-8 (scene): S" in text
    assert "exactly 2 paragraphs" in NarrationPlan([Slot("a", "x", 2)]).describe()


def test_plan_rejects_a_variable_slot_that_is_not_last():
    with pytest.raises(PromptError, match="only the last"):
        NarrationPlan([Slot("a", "x", 1, 2), Slot("b", "y", 1)])
    with pytest.raises(PromptError):
        NarrationPlan([])
    with pytest.raises(PromptError):
        Slot("a", "x", 3, 2)


class Extra(BaseModel):
    changes: list[str] = []
    check: bool = False


def test_reply_model_puts_narration_first_and_enforces_the_count():
    model = NarrationPlan([Slot("a", "x", 2)]).reply_model(Extra)
    assert list(model.model_fields) == ["narration", "changes", "check"]
    assert model(narration=["one", "two"]).changes == []
    for bad in (["one"], ["1", "2", "3"]):
        with pytest.raises(ValidationError):
            model(narration=bad)


def test_request_carries_the_plan_schema(builder):
    request = builder.build("demo", STATIC, STATE).request(schema=Extra)
    narration = request.schema.model_json_schema()["properties"]["narration"]
    assert list(request.schema.model_fields)[0] == "narration"
    assert (narration["minItems"], narration["maxItems"]) == (3, 5)


def test_bad_recipes_are_errors(tmp_path):
    for name, text, message in [("a", "id = 'x'\ntask = 't'", "needs 'system'"), ("b", "system = []", "missing"), ("c", "id = [", "not valid TOML")]:
        path = tmp_path / f"{name}.toml"
        path.write_text(text)
        with pytest.raises(PromptError, match=message):
            load_recipe(path)


class Values(Mapping):
    """Supplies a value for any placeholder, and the given classification."""

    def __init__(self, classification):
        self.classification = classification

    def __getitem__(self, key):
        return self.classification if key == "classification" else "x"

    def __contains__(self, key):
        return True

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 1


@pytest.mark.parametrize("classification", ["critical_failure", "failure", "narrow_success", "success", "critical_success"])
def test_shipped_library_builds_every_recipe_and_variant(classification):
    builder = PromptBuilder.from_directory(LIBRARY)
    for path in sorted((LIBRARY / "recipes").glob("*.toml")):
        recipe = builder.recipe(path.stem)
        for variant in recipe.variants:
            values = Values(classification)
            prompt = builder.build(recipe.id, values, values, variant=variant)
            assert prompt.system and (prompt.plan is None or prompt.plan.max >= 1)


def test_check_outcome_picks_the_instruction_for_the_classification():
    builder = PromptBuilder.from_directory(LIBRARY)
    state = {"world_state": "w", "character": "c", "roll": 1, "skill": "Stealth", "difficulty": 12, "margin": -11, "tier": "easy"}
    low = builder.build("check_outcome", state=state | {"classification": "critical_failure"})
    high = builder.build("check_outcome", state=state | {"classification": "critical_success"})
    assert "critical failure" in low.state and "critical success" in high.state
    assert low.system == high.system


def test_recipe_without_a_plan_has_no_narration_and_uses_the_schema_as_given(tmp_path):
    (tmp_path / "fragments").mkdir()
    (tmp_path / "fragments" / "a.md").write_text("Hello {x}.")
    (tmp_path / "recipes").mkdir()
    (tmp_path / "recipes" / "r.toml").write_text('id = "r"\nsystem = ["a"]\nstate = ["a"]\n')
    prompt = PromptBuilder.from_directory(tmp_path).build("r", {"x": 1}, {"x": 2})
    assert prompt.plan is None and prompt.system == "Hello 1." and "paragraph" not in prompt.system
    assert prompt.request(schema=Extra).schema is Extra


def test_opening_introduces_the_player_character_and_the_narrator_is_told_who_they_are():
    prompt = PromptBuilder.from_directory(LIBRARY).build("opening", state={"world_state": "w", "character": "c"})
    assert "Introduce the player's character" in prompt.system
    assert 'the person you address as "you"' in prompt.system
