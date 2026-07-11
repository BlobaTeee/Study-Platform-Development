import pandas as pd
import pytest


@pytest.fixture
def sciq_raw_df():
    """Tiny SciQ-shaped frame: 3 questions, one with empty support."""
    return pd.DataFrame(
        {
            "question": ["What gas do plants absorb?", "What is water made of?", "Speed unit?"],
            "correct_answer": ["carbon dioxide", "hydrogen and oxygen", "meters per second"],
            "distractor1": ["oxygen", "helium", "kilograms"],
            "distractor2": ["nitrogen", "carbon", "seconds"],
            "distractor3": ["argon", "iron", "newtons"],
            "support": [
                "Plants absorb carbon dioxide from the air during photosynthesis.",
                "Water is made of hydrogen and oxygen atoms.",
                "   ",  # empty/whitespace support -> dropped
            ],
        }
    )


@pytest.fixture
def aif_raw_df():
    """Tiny AI-Flashcards-shaped frame with en/ur rows and a duplicate."""
    base = {
        "subject": "Mathematics",
        "topic": "Calculus",
        "subtopic": "Continuity",
        "difficulty": "hard",
        "bloom_level": "Understand",
        "cognitive_skill": "Comprehension",
        "source_type": "lecture_note",
        "source_text": "Continuity is a key concept in Calculus.",
        "summary": "Summary of continuity.",
        "question": "What is Continuity?",
        "answer": "A core concept.",
        "token_estimate": 40,
    }
    rows = [
        {**base, "language": "en"},
        {**base, "language": "en"},  # exact duplicate -> deduped
        {**base, "language": "ur", "source_text": "Continuity [ur]"},
        {**base, "subtopic": "Limits", "language": "en", "source_text": "Limits in Calculus."},
    ]
    return pd.DataFrame([{"id": i, **r} for i, r in enumerate(rows)])


@pytest.fixture
def guidance_hierarchy_df():
    """Tiny topic hierarchy: 2 subjects, 4 subtopics with coverage counts."""
    return pd.DataFrame([
        {"subject": "Mathematics", "topic": "Calculus", "subtopic": "Continuity", "count": 30},
        {"subject": "Mathematics", "topic": "Calculus", "subtopic": "Limits", "count": 50},
        {"subject": "Mathematics", "topic": "Algebra", "subtopic": "Polynomials", "count": 20},
        {"subject": "Physics", "topic": "Mechanics", "subtopic": "Kinematics", "count": 40},
    ])


@pytest.fixture
def guidance_flashcards_df():
    """Tiny flashcards frame with difficulty labels + question text per subtopic."""
    return pd.DataFrame([
        {"subject": "Mathematics", "topic": "Calculus", "subtopic": "Continuity",
         "difficulty": "hard", "question": "What is continuity of a function?"},
        {"subject": "Mathematics", "topic": "Calculus", "subtopic": "Continuity",
         "difficulty": "hard", "question": "Define a continuous limit at a point."},
        {"subject": "Mathematics", "topic": "Calculus", "subtopic": "Limits",
         "difficulty": "easy", "question": "What is the limit of a sequence?"},
        {"subject": "Mathematics", "topic": "Algebra", "subtopic": "Polynomials",
         "difficulty": "medium", "question": "What is the degree of a polynomial?"},
        {"subject": "Physics", "topic": "Mechanics", "subtopic": "Kinematics",
         "difficulty": "medium", "question": "What is velocity in kinematics?"},
    ])


# Generation fixtures (ContentExtractor, generators)
from ml_pipeline.services.content_extractor import Candidate


@pytest.fixture
def sample_candidates():
    """Deterministic Candidates for generator unit tests (no spaCy needed)."""
    return [
        Candidate(sentence="Mitochondria are the powerhouse of the cell.",
                  term="powerhouse", label="NOUN_CHUNK", score=3.0),
        Candidate(sentence="Albert Einstein developed the theory of relativity.",
                  term="Albert Einstein", label="PERSON", score=2.5),
        Candidate(sentence="Photosynthesis converts sunlight into chemical energy.",
                  term="Photosynthesis", label="NOUN_CHUNK", score=2.0),
        Candidate(sentence="Water boils at 100 degrees Celsius at sea level.",
                  term="100 degrees Celsius", label="QUANTITY", score=1.5),
    ]


class FakeExtractor:
    """Returns a fixed candidate list, ignoring the text."""
    def __init__(self, candidates):
        self._candidates = candidates

    def extract_candidates(self, text, max_candidates):
        return list(self._candidates)[:max_candidates]


class FakeScorer:
    """Deterministic AnswerScorer stub. Ranks `winner` first if present."""
    def __init__(self, winner=None):
        self.winner = winner

    def rank(self, question, candidates, support):
        cands = list(candidates)
        if self.winner in cands:
            cands = [self.winner] + [c for c in cands if c != self.winner]
        return [(c, 1.0 - i * 0.1) for i, c in enumerate(cands)]


@pytest.fixture
def fake_extractor_factory():
    return FakeExtractor


@pytest.fixture
def fake_scorer_factory():
    return FakeScorer
