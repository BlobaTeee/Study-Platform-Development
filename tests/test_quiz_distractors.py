from ml_pipeline.services.content_extractor import Candidate
from ml_pipeline.services.quiz_generator import QuizGenerator


def _cands():
    return [
        Candidate("A sentence about dogs.", "dog", "NOUN_CHUNK", 3.0),
        Candidate("A sentence about cats.", "cat", "NOUN_CHUNK", 2.5),
        Candidate("A sentence about birds.", "bird", "NOUN_CHUNK", 2.0),
        Candidate("A sentence about fish.", "fish", "NOUN_CHUNK", 1.5),
        Candidate("Paris is a city.", "Paris", "GPE", 1.0),
    ]


def test_distractors_exclude_correct_and_are_from_source():
    cands = _cands()
    correct = cands[0]  # "dog"
    distractors = QuizGenerator._distractors(correct, cands)
    assert "dog" not in [d.lower() for d in distractors]
    source_terms = {c.term for c in cands}
    assert all(d in source_terms for d in distractors)


def test_distractors_prefer_same_label():
    cands = _cands()
    correct = cands[0]  # NOUN_CHUNK
    distractors = QuizGenerator._distractors(correct, cands)[:3]
    # top distractors should be the other NOUN_CHUNK terms, not the GPE "Paris"
    assert "Paris" not in distractors


def test_distractors_deduped():
    cands = [
        Candidate("s1", "dog", "NOUN_CHUNK", 3.0),
        Candidate("s2", "Dog", "NOUN_CHUNK", 2.0),  # dup by case
        Candidate("s3", "cat", "NOUN_CHUNK", 1.0),
    ]
    distractors = QuizGenerator._distractors(cands[0], cands)
    assert [d.lower() for d in distractors].count("dog") == 0
