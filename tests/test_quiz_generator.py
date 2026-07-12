from ml_pipeline.services.content_extractor import Candidate
from ml_pipeline.services.quiz_generator import QuizGenerator


def _cands():
    return [
        Candidate("Mitochondria are the powerhouse of the cell.", "powerhouse", "NOUN_CHUNK", 3.0),
        Candidate("Ribosomes build proteins in the cell.", "Ribosomes", "NOUN_CHUNK", 2.5),
        Candidate("The nucleus stores genetic material.", "nucleus", "NOUN_CHUNK", 2.0),
        Candidate("Chloroplasts perform photosynthesis.", "Chloroplasts", "NOUN_CHUNK", 1.5),
    ]


def _gen(cands, winner, fake_extractor_factory, fake_scorer_factory):
    return QuizGenerator(extractor=fake_extractor_factory(cands),
                         scorer=fake_scorer_factory(winner=winner))


def test_valid_mcq_shape_when_gate_passes(fake_extractor_factory, fake_scorer_factory):
    cands = _cands()
    gen = _gen(cands, "powerhouse", fake_extractor_factory, fake_scorer_factory)
    data = gen.generate("ignored", question_count=1)
    assert set(data) == {"title", "description", "questions"}
    q = data["questions"][0]
    assert set(q) == {"question_text", "question_type", "options", "correct_answer", "explanation"}
    assert q["question_type"] == "multiple_choice"
    assert len(q["options"]) == 4
    assert q["correct_answer"] == "powerhouse"
    assert q["correct_answer"] in q["options"]
    assert "______" in q["question_text"]
    assert q["explanation"] == "Mitochondria are the powerhouse of the cell."


def test_gate_drops_question_when_correct_not_ranked_first(fake_extractor_factory, fake_scorer_factory):
    cands = _cands()
    # scorer makes a DISTRACTOR win -> every question should be dropped
    gen = _gen(cands, "Ribosomes", fake_extractor_factory, fake_scorer_factory)
    data = gen.generate("ignored", question_count=4)
    # "powerhouse" question: winner "Ribosomes" is a distractor -> dropped.
    # Only a question whose correct term == "Ribosomes" could survive.
    for q in data["questions"]:
        assert q["correct_answer"] == "Ribosomes"


def test_quality_over_quantity_returns_fewer(fake_extractor_factory, fake_scorer_factory):
    # Only two candidates -> can't form 3 distractors -> no valid questions.
    cands = [
        Candidate("A about x.", "x", "NOUN_CHUNK", 2.0),
        Candidate("B about y.", "y", "NOUN_CHUNK", 1.0),
    ]
    gen = _gen(cands, "x", fake_extractor_factory, fake_scorer_factory)
    assert gen.generate("ignored", question_count=5)["questions"] == []


def test_zero_count_returns_empty_questions(fake_extractor_factory, fake_scorer_factory):
    gen = _gen(_cands(), "powerhouse", fake_extractor_factory, fake_scorer_factory)
    assert gen.generate("ignored", question_count=0)["questions"] == []


def test_quiz_generation_is_deterministic(fake_extractor_factory, fake_scorer_factory):
    a = _gen(_cands(), "powerhouse", fake_extractor_factory, fake_scorer_factory)
    b = _gen(_cands(), "powerhouse", fake_extractor_factory, fake_scorer_factory)
    out_a = a.generate("ignored", question_count=4)
    out_b = b.generate("ignored", question_count=4)
    assert out_a == out_b  # seeded shuffle -> identical options order
