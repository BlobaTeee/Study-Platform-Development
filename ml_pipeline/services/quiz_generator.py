"""Quiz (MCQ) generation from source text, gated by the trained AnswerScorer."""
from __future__ import annotations

import random
from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer

from .. import config
from ..answer_scorer import AnswerScorer
from .content_extractor import ContentExtractor

OVERSAMPLE = 4
N_DISTRACTORS = 3
BLANK = "______"


@lru_cache(maxsize=1)
def get_answer_scorer() -> AnswerScorer:
    """Memoized trained AnswerScorer. Raises if the artifact is missing."""
    return AnswerScorer.load(config.MODELS_DIR / "answer_scorer.joblib")


class QuizGenerator:
    def __init__(self, extractor=None, scorer=None):
        self._extractor = extractor
        self._scorer = scorer

    @property
    def extractor(self):
        return self._extractor if self._extractor is not None else ContentExtractor()

    @property
    def scorer(self):
        return self._scorer if self._scorer is not None else get_answer_scorer()

    @staticmethod
    def _distractors(candidate, candidates) -> list[str]:
        """Same-source terms, same label first, TF-IDF-ranked WITHIN each group so
        the same-label preference is preserved (not washed out by a global re-sort)."""
        same, other, seen = [], [], {candidate.term.lower()}
        for c in candidates:
            key = c.term.lower()
            if key in seen:
                continue
            seen.add(key)
            (same if c.label == candidate.label else other).append(c.term)
        return (QuizGenerator._rank_by_similarity(candidate.term, same)
                + QuizGenerator._rank_by_similarity(candidate.term, other))

    @staticmethod
    def _rank_by_similarity(term: str, terms: list[str]) -> list[str]:
        """Order `terms` by TF-IDF cosine similarity to `term` (desc, name tie-break)."""
        if len(terms) < 2:
            return list(terms)
        try:
            vec = TfidfVectorizer().fit([term] + terms)
            tm = vec.transform([term])
            om = vec.transform(terms)
            sims = (om @ tm.T).toarray().ravel()
        except ValueError:
            return list(terms)
        order = sorted(range(len(terms)), key=lambda i: (-sims[i], terms[i]))
        return [terms[i] for i in order]
