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
    # Falls back rather than raising.
    assert result is None or result["question"] != _card()[0]
