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


def test_empty_profile_is_valid(guidance_hierarchy_df, guidance_flashcards_df):
    eng = _engine(guidance_hierarchy_df, guidance_flashcards_df)
    profile = eng.build_performance_profile(flashcards=[], quiz_attempts=[])
    assert profile == {"by_topic": {}, "overall_accuracy": None}
