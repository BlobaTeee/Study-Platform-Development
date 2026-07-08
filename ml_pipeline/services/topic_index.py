"""Shared topic index for the guidance engines.

Loads the processed parquet once, builds a TF-IDF index over the topic
hierarchy, and aggregates a difficulty label per subtopic from the flashcards
dataset. Framework-free and classical (scikit-learn TF-IDF only).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer

from .. import config

_DIFFICULTY_RANK = {"easy": 0, "medium": 1, "hard": 2}
_SAMPLE_QUESTIONS_PER_SUBTOPIC = 20


@dataclass(frozen=True)
class TopicRow:
    subject: str
    topic: str
    subtopic: str
    count: int
    difficulty: str


def _majority_difficulty(values) -> str:
    """Most common valid difficulty label; ties break to the easier label."""
    vals = [str(v).strip().lower() for v in values]
    vals = [v for v in vals if v in _DIFFICULTY_RANK]
    if not vals:
        return "medium"
    counts = Counter(vals)
    best = max(counts.items(), key=lambda kv: (kv[1], -_DIFFICULTY_RANK[kv[0]]))
    return best[0]


class TopicIndex:
    def __init__(self, rows, vectorizer, matrix):
        self._rows = rows
        self._vectorizer = vectorizer
        self._matrix = matrix  # TF-IDF matrix aligned row-for-row with self._rows

    @classmethod
    def from_frames(cls, hierarchy_df, flashcards_df) -> "TopicIndex":
        diff_map, q_map = {}, {}
        if flashcards_df is not None and len(flashcards_df):
            has_diff = "difficulty" in flashcards_df.columns
            has_q = "question" in flashcards_df.columns
            group_cols = ["subject", "topic", "subtopic"]
            if all(c in flashcards_df.columns for c in group_cols):
                for key, grp in flashcards_df.groupby(group_cols):
                    if has_diff:
                        diff_map[key] = _majority_difficulty(grp["difficulty"])
                    if has_q:
                        q_map[key] = " ".join(
                            str(x) for x in grp["question"].head(_SAMPLE_QUESTIONS_PER_SUBTOPIC)
                        )

        rows, corpus = [], []
        for r in hierarchy_df.itertuples(index=False):
            key = (r.subject, r.topic, r.subtopic)
            rows.append(TopicRow(
                subject=r.subject, topic=r.topic, subtopic=r.subtopic,
                count=int(getattr(r, "count", 0) or 0),
                difficulty=diff_map.get(key, "medium"),
            ))
            corpus.append(f"{r.subject} {r.topic} {r.subtopic} {q_map.get(key, '')}".strip())

        vectorizer = TfidfVectorizer(
            max_features=config.TFIDF_MAX_FEATURES,
            ngram_range=config.TFIDF_NGRAM,
            stop_words="english",
        )
        matrix = vectorizer.fit_transform(corpus) if corpus else None
        return cls(rows, vectorizer, matrix)

    @classmethod
    def load(cls) -> "TopicIndex":
        from ..dataset_loader import load_processed
        return cls.from_frames(load_processed("topic_hierarchy"), load_processed("flashcards"))

    def search(self, text: str, n: int):
        if not text or not text.strip() or self._matrix is None:
            return []
        q = self._vectorizer.transform([text])
        sims = (self._matrix @ q.T).toarray().ravel()  # TF-IDF is L2-normed => cosine
        order = sorted(range(len(self._rows)), key=lambda i: (-sims[i], self._rows[i].subtopic))
        return [(self._rows[i], float(sims[i])) for i in order[:n] if sims[i] > 0]

    def top_by_coverage(self, n: int):
        return sorted(self._rows, key=lambda r: (-r.count, r.subtopic))[:n]

    def rows_for_subject(self, subject: str):
        return [r for r in self._rows if r.subject == subject]

    def subjects(self):
        return sorted({r.subject for r in self._rows})

    def default_subject(self):
        if not self._rows:
            return None
        totals = defaultdict(int)
        for r in self._rows:
            totals[r.subject] += r.count
        return max(sorted(totals), key=lambda s: totals[s])

    def difficulty_for(self, subject, topic, subtopic) -> str:
        for r in self._rows:
            if (r.subject, r.topic, r.subtopic) == (subject, topic, subtopic):
                return r.difficulty
        return "medium"


@lru_cache(maxsize=1)
def get_topic_index() -> TopicIndex:
    """Process-memoized singleton. Raises if the processed parquet is missing."""
    return TopicIndex.load()
