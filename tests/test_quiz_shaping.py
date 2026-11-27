"""Unit tests for quiz-question shaping (guarantees answerable MCQs)."""
import importlib.util
import random
from pathlib import Path

import pytest

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "notebooks" / "services" / "quiz_shaping.py")


def _load():
    # Loaded inside a stand-in package so its relative import of `.units`
    # (a sibling with no Django dependency) resolves without Django.
    import sys
    import types
    package = "services_under_test"
    if package not in sys.modules:
        stand_in = types.ModuleType(package)
        stand_in.__path__ = [str(_MODULE_PATH.parent)]
        sys.modules[package] = stand_in
    spec = importlib.util.spec_from_file_location(f"{package}.quiz_shaping", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


qs = _load()


def _rng():
    return random.Random(0)


def test_distractor_schema_builds_four_answerable_options():
    raw = {"question_text": "Capital of France?", "correct_answer": "Paris",
           "distractors": ["London", "Berlin", "Rome"], "explanation": "It's Paris."}
    out = qs.shape_quiz_question(raw, _rng())
    assert out["question_type"] == "multiple_choice"
    assert set(out["options"]) == {"Paris", "London", "Berlin", "Rome"}
    assert out["correct_answer"] == "Paris"
    assert out["correct_answer"] in out["options"]        # the whole point
    assert out["explanation"] == "It's Paris."


def test_correct_answer_always_in_options_even_if_model_omitted_it():
    # The exact 3B failure: model lists options WITHOUT the correct answer.
    raw = {"question_text": "Q?", "correct_answer": "Right",
           "options": ["Wrong1", "Wrong2", "Wrong3"]}
    out = qs.shape_quiz_question(raw, _rng())
    assert out["correct_answer"] in out["options"]
    assert "Right" in out["options"]


def test_back_compat_options_schema_with_correct_present():
    raw = {"question_text": "Q?", "correct_answer": "B",
           "options": ["A", "B", "C", "D"]}
    out = qs.shape_quiz_question(raw, _rng())
    assert set(out["options"]) == {"A", "B", "C", "D"}
    assert out["correct_answer"] == "B"


def test_caps_to_four_options():
    raw = {"question_text": "Q?", "correct_answer": "c",
           "distractors": ["d1", "d2", "d3", "d4", "d5"]}
    out = qs.shape_quiz_question(raw, _rng())
    assert len(out["options"]) == 4
    assert "c" in out["options"]


def test_drops_distractors_equal_to_correct_and_duplicates():
    raw = {"question_text": "Q?", "correct_answer": "x",
           "distractors": ["x", "y", "y", "z"]}
    out = qs.shape_quiz_question(raw, _rng())
    assert sorted(out["options"]) == ["x", "y", "z"]


def test_none_when_no_distractors_or_options():
    raw = {"question_text": "Q?", "correct_answer": "x", "distractors": []}
    assert qs.shape_quiz_question(raw, _rng()) is None


def test_none_when_missing_question_or_answer():
    assert qs.shape_quiz_question({"correct_answer": "x", "distractors": ["y"]}, _rng()) is None
    assert qs.shape_quiz_question({"question_text": "Q?", "distractors": ["y"]}, _rng()) is None


def test_accepts_alternate_keys():
    raw = {"question": "Q?", "answer": "x", "distractors": ["y", "z"]}
    out = qs.shape_quiz_question(raw, _rng())
    assert out["question_text"] == "Q?"
    assert out["correct_answer"] == "x"
    assert "x" in out["options"]


# ---- option-letter prefixes -------------------------------------------------------
# Some models answer "C) Creating engaging interfaces…" with distractors
# "A) …", "B) …". Stored like that, the letters break exact-match grading and
# the typed-answer grader, and the review shows them. They are not content.

def test_strip_option_prefix_handles_the_common_shapes():
    for raw in ("C) Creating engaging interfaces", "c) Creating engaging interfaces",
                "(C) Creating engaging interfaces", "C. Creating engaging interfaces",
                "C: Creating engaging interfaces", "  B)  Creating engaging interfaces "):
        assert qs.strip_option_prefix(raw) == "Creating engaging interfaces", raw


def test_strip_option_prefix_leaves_real_answers_alone():
    for raw in ("A protein", "B cells", "C++ templates", "D-day", "Accountability", "12"):
        assert qs.strip_option_prefix(raw) == raw, raw


def test_shaping_strips_prefixes_from_answer_and_distractors():
    out = qs.shape_quiz_question(
        {"question_text": "Focus of IxD?", "correct_answer": "C) Engaging interfaces",
         "distractors": ["A) Pretty graphics", "B) Open-source software", "D) Fast databases"]},
        _rng())
    assert out["correct_answer"] == "Engaging interfaces"
    assert set(out["options"]) == {"Engaging interfaces", "Pretty graphics", "Open-source software", "Fast databases"}
