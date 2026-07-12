"""End-to-end against real spaCy + the real trained AnswerScorer.

Skips cleanly if the model artifact has not been built yet.
"""
import pytest

from ml_pipeline import config
from ml_pipeline.services import FlashcardGenerator, QuizGenerator

_TEXT = (
    "Mitochondria are the powerhouse of the cell, producing energy through respiration. "
    "Ribosomes are responsible for building proteins from amino acids. "
    "The nucleus stores the genetic material of the cell in the form of DNA. "
    "Chloroplasts carry out photosynthesis, converting sunlight into chemical energy. "
    "Photosynthesis occurs in the leaves of green plants and produces oxygen. "
    "The cell membrane controls what enters and leaves the cell."
)


def test_flashcards_have_valid_shape_on_real_text():
    cards = FlashcardGenerator().generate(_TEXT, count=5)
    assert cards, "expected non-empty flashcards on a rich paragraph"
    for c in cards:
        assert set(c) == {"question", "answer", "difficulty"}
        assert c["question"] and c["answer"]
        assert c["difficulty"] in {"easy", "medium", "hard"}


@pytest.mark.skipif(
    not (config.MODELS_DIR / "answer_scorer.joblib").exists(),
    reason="trained answer_scorer.joblib not present",
)
def test_quiz_questions_pass_scorer_gate_on_real_text():
    data = QuizGenerator().generate(_TEXT, question_count=4)
    assert set(data) == {"title", "description", "questions"}
    for q in data["questions"]:
        assert set(q) == {"question_text", "question_type", "options",
                          "correct_answer", "explanation"}
        assert len(q["options"]) == 4
        assert q["correct_answer"] in q["options"]
        assert "______" in q["question_text"]


def test_generation_is_deterministic():
    a = FlashcardGenerator().generate(_TEXT, count=5)
    b = FlashcardGenerator().generate(_TEXT, count=5)
    assert a == b
