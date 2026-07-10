"""End-to-end against the REAL processed parquet (datasets/processed/*.parquet).

Skips cleanly if the processed data has not been built yet.
"""
import pytest

from ml_pipeline import config
from ml_pipeline.services import LearningPathEngine, RecommendationEngine
from ml_pipeline.services.topic_index import TopicIndex

pytestmark = pytest.mark.skipif(
    not config.PROCESSED_FILES["topic_hierarchy"].exists()
    or not config.PROCESSED_FILES["flashcards"].exists(),
    reason="processed parquet not built yet",
)


@pytest.fixture(scope="module")
def real_index():
    return TopicIndex.load()


def test_recommendations_have_valid_shape_on_real_data(real_index):
    eng = RecommendationEngine(index=real_index)
    # Query with a real topic+subtopic drawn from the index, so the relevance
    # assertion is independent of the actual taxonomy contents.
    sample = real_index.top_by_coverage(1)[0]
    recs = eng.recommend_from_text(
        f"{sample.topic} {sample.subtopic}", performance_by_topic={}, n=5)
    assert recs, "expected non-empty recommendations on real data"
    for r in recs:
        assert set(r) == {
            "subject", "topic", "subtopic", "label",
            "priority", "recommended_difficulty", "reason",
        }
        assert r["recommended_difficulty"] in {"easy", "medium", "hard"}
    # querying a real topic surfaces that topic/subtopic in the top results
    assert any(
        r["topic"] == sample.topic or r["subtopic"] == sample.subtopic for r in recs)


def test_cold_recommendations_non_empty_on_real_data(real_index):
    eng = RecommendationEngine(index=real_index)
    recs = eng.recommend_from_text("", performance_by_topic={}, n=5)
    assert len(recs) == 5


def test_learning_path_valid_shape_on_real_data(real_index):
    eng = LearningPathEngine(index=real_index)
    path = eng.get_learning_path(subject=None, mastered_subtopics=set(), limit=12)
    assert path, "expected a non-empty default-subject path"
    statuses = {s["status"] for s in path}
    assert statuses <= {"mastered", "current", "upcoming"}
    assert [s["step"] for s in path] == list(range(1, len(path) + 1))
