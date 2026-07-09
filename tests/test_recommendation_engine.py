from collections import namedtuple

from ml_pipeline.services.recommendation_engine import RecommendationEngine
from ml_pipeline.services.topic_index import TopicIndex

_Topic = namedtuple("Topic", ["name"])
_Card = namedtuple("Card", ["correct_count", "incorrect_count", "topic"])
_Quiz = namedtuple("Quiz", ["topic"])
_Attempt = namedtuple("Attempt", ["score", "quiz"])


def _engine(guidance_hierarchy_df, guidance_flashcards_df):
    idx = TopicIndex.from_frames(guidance_hierarchy_df, guidance_flashcards_df)
    return RecommendationEngine(index=idx)


def test_profile_aggregates_flashcard_accuracy(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    cards = [
        _Card(correct_count=2, incorrect_count=8, topic=_Topic("Calculus")),  # 0.2
        _Card(correct_count=9, incorrect_count=1, topic=_Topic("Algebra")),   # 0.9
        _Card(correct_count=0, incorrect_count=0, topic=_Topic("Ignored")),   # no data -> skipped
    ]
    profile = eng.build_performance_profile(flashcards=cards, quiz_attempts=[])
    assert profile["by_topic"]["calculus"]["accuracy"] == 0.2
    assert profile["by_topic"]["algebra"]["accuracy"] == 0.9
    assert "ignored" not in profile["by_topic"]
    assert profile["overall_accuracy"] == 0.55


def test_profile_includes_quiz_scores(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    attempts = [_Attempt(score=40.0, quiz=_Quiz(topic=_Topic("Mechanics")))]  # 0.4
    profile = eng.build_performance_profile(flashcards=[], quiz_attempts=attempts)
    assert profile["by_topic"]["mechanics"]["accuracy"] == 0.4


def test_low_percentage_quiz_score_is_treated_as_percent(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    attempts = [_Attempt(score=5.0, quiz=_Quiz(topic=_Topic("Mechanics")))]  # 5% -> 0.05
    profile = eng.build_performance_profile(flashcards=[], quiz_attempts=attempts)
    assert profile["by_topic"]["mechanics"]["accuracy"] == 0.05


def test_empty_profile_is_valid(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    profile = eng.build_performance_profile(flashcards=[], quiz_attempts=[])
    assert profile == {"by_topic": {}, "overall_accuracy": None}


def test_warm_path_ranks_relevant_subtopic_top(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    recs = eng.recommend_from_text("continuity of a function", performance_by_topic={}, n=3)
    assert recs
    assert recs[0]["subtopic"] == "Continuity"
    assert set(recs[0]) == {
        "subject", "topic", "subtopic", "label",
        "priority", "recommended_difficulty", "reason",
    }
    assert recs[0]["recommended_difficulty"] in {"easy", "medium", "hard"}


def test_cold_path_returns_coverage_order(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    recs = eng.recommend_from_text("", performance_by_topic={}, n=2)
    assert [r["subtopic"] for r in recs] == ["Limits", "Kinematics"]  # counts 50, 40
    assert all("Foundational" in r["reason"] for r in recs)


def test_weakness_weighting_boosts_priority(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)

    def poly_priority(recs):
        return next(r["priority"] for r in recs if r["subtopic"] == "Polynomials")

    neutral = eng.recommend_from_text("", performance_by_topic={}, n=4)
    # Algebra (Polynomials' parent topic) is weak -> Polynomials should be boosted.
    weak = {"by_topic": {"algebra": {"n": 5, "accuracy": 0.1}}, "overall_accuracy": 0.1}
    boosted = eng.recommend_from_text("", performance_by_topic=weak, n=4)

    assert poly_priority(boosted) > poly_priority(neutral)
    poly = next(r for r in boosted if r["subtopic"] == "Polynomials")
    assert "scoring lower" in poly["reason"]


def test_recommend_empty_when_index_has_no_rows():
    import pandas as pd
    from ml_pipeline.services.topic_index import TopicIndex
    empty = TopicIndex.from_frames(
        pd.DataFrame(columns=["subject", "topic", "subtopic", "count"]), pd.DataFrame())
    eng = RecommendationEngine(index=empty)
    assert eng.recommend_from_text("anything", performance_by_topic={}, n=5) == []
