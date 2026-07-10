"""Adaptive learning path over the topic hierarchy. Framework-free.

Orders a subject's subtopics easy -> hard, then by coverage, and marks each as
mastered / current / upcoming based on the student's estimated mastery.
"""
from __future__ import annotations

from .topic_index import TopicIndex, get_topic_index

MASTERY_THRESHOLD = 0.8
MIN_MASTERY_POINTS = 2
DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}


class LearningPathEngine:
    def __init__(self, index: TopicIndex | None = None):
        self._index = index

    @property
    def index(self) -> TopicIndex:
        return self._index if self._index is not None else get_topic_index()

    def estimate_mastery_from_performance(self, profile: dict) -> set:
        by_topic = (profile or {}).get("by_topic", {})
        return {
            key for key, stat in by_topic.items()
            if stat.get("n", 0) >= MIN_MASTERY_POINTS
            and stat.get("accuracy", 0.0) >= MASTERY_THRESHOLD
        }

    def get_learning_path(self, subject=None, mastered_subtopics=None, limit: int = 15) -> list[dict]:
        idx = self.index
        limit = max(0, limit)
        subject = subject or idx.default_subject()
        if not subject:
            return []
        rows = idx.rows_for_subject(subject)
        if not rows:
            return []

        mastered = {str(m).strip().lower() for m in (mastered_subtopics or [])}
        ordered = sorted(
            rows, key=lambda r: (DIFFICULTY_ORDER.get(r.difficulty, 1), -r.count, r.subtopic))

        steps, current_assigned = [], False
        for i, row in enumerate(ordered[:limit], start=1):
            is_mastered = (
                row.subtopic.strip().lower() in mastered
                or row.topic.strip().lower() in mastered
            )
            if is_mastered:
                status = "mastered"
            elif not current_assigned:
                status = "current"
                current_assigned = True
            else:
                status = "upcoming"
            steps.append({
                "step": i,
                "subject": row.subject,
                "topic": row.topic,
                "subtopic": row.subtopic,
                "difficulty": row.difficulty,
                "status": status,
            })
        return steps
