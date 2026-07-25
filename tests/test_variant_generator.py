"""The variant generator: a failed card becomes a different question."""
import importlib.util
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
_MODULE_PATH = _BACKEND_DIR / "flashcards" / "services" / "variant_generator.py"


def _load():
    # The module under test imports `notebooks.services.dedupe`, which resolves
    # the way it does under Django: with backend/ on the path. Adding it here
    # keeps the module loadable standalone, without importing Django itself.
    if str(_BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(_BACKEND_DIR))
    spec = importlib.util.spec_from_file_location("variant_generator_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vg = _load()


class FakeProvider:
    """Returns queued payloads; raises if it runs out."""

    def __init__(self, *payloads):
        self._payloads = list(payloads)
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        if not self._payloads:
            raise RuntimeError("provider exhausted")
        payload = self._payloads.pop(0)
        if isinstance(payload, Exception):
            raise payload
        return payload


def _card():
    return "What is photosynthesis?", "Conversion of light into chemical energy"


def test_returns_a_question_different_from_the_original():
    provider = FakeProvider({"question": "Which gas do plants release during photosynthesis?",
                             "answer": "Oxygen"})
    result = vg.generate_variant(*_card(), provider=provider)
    assert result["question"] == "Which gas do plants release during photosynthesis?"
    assert result["answer"] == "Oxygen"
    assert result["difficulty"] in ("easy", "medium", "hard")


def test_excerpt_is_included_in_the_prompt():
    provider = FakeProvider({"question": "Q?", "answer": "A"})
    vg.generate_variant(*_card(), provider=provider, excerpt="Chlorophyll absorbs light.")
    assert "Chlorophyll absorbs light." in provider.prompts[0]


def test_a_variant_matching_the_original_is_retried_then_falls_back():
    original_q, original_a = _card()
    # First reply repeats the original question; the retry gives a real variant.
    provider = FakeProvider({"question": original_q, "answer": original_a},
                            {"question": "Photosynthesis stores energy in what form?",
                             "answer": "Chemical bonds"})
    result = vg.generate_variant(original_q, original_a, provider=provider)
    assert result["question"] == "Photosynthesis stores energy in what form?"
    assert len(provider.prompts) == 2


def test_provider_failure_falls_back_to_a_reformat():
    provider = FakeProvider(RuntimeError("ollama down"), RuntimeError("still down"))
    result = vg.generate_variant(*_card(), provider=provider)
    assert result is not None
    assert result["question"] != _card()[0]


def test_returns_none_when_nothing_usable_can_be_produced():
    provider = FakeProvider(RuntimeError("down"), RuntimeError("down"))
    # Too short to reformat into anything meaningful.
    assert vg.generate_variant("Q?", "", provider=provider) is None


def test_reformat_fallback_turns_a_definition_into_a_cloze():
    result = vg.reformat_fallback("What is photosynthesis?",
                                  "Conversion of light into chemical energy")
    assert result is not None
    assert "______" in result["question"]
    assert result["answer"] == "Photosynthesis" or result["answer"]


def test_malformed_payload_is_treated_as_a_failure():
    provider = FakeProvider({"nonsense": True}, {"nonsense": True})
    result = vg.generate_variant(*_card(), provider=provider)
    # Both malformed replies must actually have been consumed by _clean() and
    # rejected — proving the result came from the fallback, not the payload
    # (a deterministic-fallback result alone doesn't distinguish the two).
    assert len(provider.prompts) == 2
    assert result is not None
    assert result["question"] != _card()[0]


def test_fallback_never_reproduces_an_already_reformatted_card():
    # A card shaped exactly like a previous fallback's output: the question is
    # `reformat_fallback`'s own template built from this same answer. Since the
    # fallback's question text is a deterministic function of `answer` alone,
    # reformatting this again would reproduce the identical question verbatim
    # if the dedupe guard didn't cover the fallback path too (Finding 1).
    answer = "Conversion of light into chemical energy"
    question = f"{answer} — which term does this describe? ({vg.BLANK})"
    provider = FakeProvider(RuntimeError("down"), RuntimeError("down"))

    result = vg.generate_variant(question, answer, provider=provider)

    assert result is None or result["question"] != question
    if result is not None:
        # And the term it picks must be a real word, not the blank itself
        # (Finding 2) — a card whose answer is "______" is garbage either way.
        assert result["answer"].strip("_") != ""


def test_reformat_fallback_does_not_pick_the_blank_as_the_answer():
    # \w matches '_', so naively taking the last regex word from a question
    # that already ends in the "(______)" blank picks the blank itself.
    result = vg.reformat_fallback(
        "Conversion of light into chemical energy — which term does this "
        f"describe? ({vg.BLANK})",
        "Photosynthesis produces the sugars a plant needs",
    )
    assert result is not None
    assert result["answer"] != "______"
    assert result["answer"].strip("_") != ""


def test_reformat_fallback_returns_none_when_only_the_blank_remains():
    result = vg.reformat_fallback("______ ______", "Twelve character answer here")
    assert result is None
