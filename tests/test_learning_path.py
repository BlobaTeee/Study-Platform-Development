from ml_pipeline.services.learning_path import LearningPathEngine
from ml_pipeline.services.topic_index import TopicIndex


def _engine(guidance_hierarchy_df, guidance_flashcards_df):
    idx = TopicIndex.from_frames(guidance_hierarchy_df, guidance_flashcards_df)
    return LearningPathEngine(index=idx)


def test_mastery_requires_threshold_and_min_points(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    profile = {"by_topic": {
        "limits": {"n": 3, "accuracy": 0.9},     # mastered
        "continuity": {"n": 1, "accuracy": 1.0},  # too few points -> not mastered
        "algebra": {"n": 5, "accuracy": 0.5},     # below threshold -> not mastered
    }, "overall_accuracy": 0.7}
    mastered = eng.estimate_mastery_from_performance(profile)
    assert mastered == {"limits"}


def test_learning_path_orders_easy_to_hard_then_coverage(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    path = eng.get_learning_path(subject="Mathematics", mastered_subtopics=set(), limit=10)
    # Mathematics subtopics: Limits(easy,50), Polynomials(medium,20), Continuity(hard,30)
    assert [s["subtopic"] for s in path] == ["Limits", "Polynomials", "Continuity"]
    assert [s["step"] for s in path] == [1, 2, 3]
    assert path[0]["status"] == "current"     # first non-mastered
    assert path[1]["status"] == "upcoming"
    assert set(path[0]) == {"step", "subject", "topic", "subtopic", "difficulty", "status"}


def test_learning_path_marks_mastered_and_current(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    path = eng.get_learning_path(subject="Mathematics", mastered_subtopics={"limits"}, limit=10)
    by_sub = {s["subtopic"]: s for s in path}
    assert by_sub["Limits"]["status"] == "mastered"
    assert by_sub["Polynomials"]["status"] == "current"  # first non-mastered
    assert by_sub["Continuity"]["status"] == "upcoming"


def test_default_subject_when_none(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    path = eng.get_learning_path(subject=None, mastered_subtopics=set(), limit=10)
    assert path and all(s["subject"] == "Mathematics" for s in path)  # highest coverage


def test_learning_path_respects_limit(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    path = eng.get_learning_path(subject="Mathematics", mastered_subtopics=set(), limit=2)
    assert len(path) == 2


def test_learning_path_empty_for_unknown_subject(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    assert eng.get_learning_path(subject="Chemistry", mastered_subtopics=set(), limit=5) == []


def test_negative_limit_returns_empty(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    assert eng.get_learning_path(subject="Mathematics", mastered_subtopics=set(), limit=-1) == []
