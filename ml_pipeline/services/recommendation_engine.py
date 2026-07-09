"""Content-based study recommendations over the topic hierarchy, weighted by
the student's performance profile. Framework-free; classical TF-IDF only.
"""
from __future__ import annotations

from .topic_index import TopicIndex, get_topic_index

CANDIDATE_MULTIPLIER = 4
WEAK_ACCURACY_THRESHOLD = 0.6
STRONG_ACCURACY_THRESHOLD = 0.85
WEAK_WEIGHT = 1.5
STRONG_WEIGHT = 0.6


class RecommendationEngine:
    def __init__(self, index: TopicIndex | None = None):
        self._index = index

    @property
    def index(self) -> TopicIndex:
        return self._index if self._index is not None else get_topic_index()

    def build_performance_profile(self, flashcards=None, quiz_attempts=None) -> dict:
        by_topic = {}   # lower_name -> [accuracy_sum, n]
        all_acc = []

        def _add(topic_name, accuracy):
            key = (topic_name or "").strip().lower() or "__untagged__"
            slot = by_topic.setdefault(key, [0.0, 0])
            slot[0] += accuracy
            slot[1] += 1
            all_acc.append(accuracy)

        for fc in (flashcards or []):
            correct = int(getattr(fc, "correct_count", 0) or 0)
            incorrect = int(getattr(fc, "incorrect_count", 0) or 0)
            seen = correct + incorrect
            if seen <= 0:
                continue
            topic = getattr(getattr(fc, "topic", None), "name", None)
            _add(topic, correct / seen)

        for qa in (quiz_attempts or []):
            score = getattr(qa, "score", None)
            if score is None:
                continue
            frac = max(0.0, min(1.0, score / 100.0))
            quiz = getattr(qa, "quiz", None)
            topic = getattr(getattr(quiz, "topic", None), "name", None)
            _add(topic, frac)

        return {
            "by_topic": {
                k: {"n": n, "accuracy": s / n}
                for k, (s, n) in by_topic.items() if n > 0
            },
            "overall_accuracy": (sum(all_acc) / len(all_acc)) if all_acc else None,
        }

    def recommend_from_text(self, study_text: str, performance_by_topic: dict = None, n: int = 5) -> list[dict]:
        idx = self.index
        by_topic = (performance_by_topic or {}).get("by_topic", {})
        k = max(1, n) * CANDIDATE_MULTIPLIER

        warm = bool(study_text and study_text.strip())
        if warm:
            candidates = list(idx.search(study_text, k))              # [(row, relevance)]
        else:
            rows = idx.top_by_coverage(k)
            max_count = max((r.count for r in rows), default=1) or 1
            candidates = [(r, r.count / max_count) for r in rows]

        scored = []
        for row, relevance in candidates:
            weight, weak = self._weakness_weight(row, by_topic)
            scored.append((relevance * weight, weak, row))

        scored.sort(key=lambda t: (-t[0], t[2].subtopic))

        out = []
        for priority, weak, row in scored[:n]:
            out.append({
                "subject": row.subject,
                "topic": row.topic,
                "subtopic": row.subtopic,
                "label": f"{row.topic} · {row.subtopic}",
                "priority": round(float(priority), 4),
                "recommended_difficulty": row.difficulty,
                "reason": self._reason(warm, weak, row),
            })
        return out

    @staticmethod
    def _weakness_weight(row, by_topic) -> tuple:
        for name in (row.subtopic, row.topic):
            entry = by_topic.get((name or "").strip().lower())
            if entry:
                acc = entry["accuracy"]
                if acc < WEAK_ACCURACY_THRESHOLD:
                    return WEAK_WEIGHT, True
                if acc >= STRONG_ACCURACY_THRESHOLD:
                    return STRONG_WEIGHT, False
                return 1.0, False
        return 1.0, False

    @staticmethod
    def _reason(warm: bool, weak: bool, row) -> str:
        if weak:
            return f"You've been scoring lower on {row.topic}"
        if warm:
            return "Closely matches your study notes"
        return f"Foundational topic in {row.subject}"
