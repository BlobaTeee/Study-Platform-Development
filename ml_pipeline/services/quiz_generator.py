"""Quiz (MCQ) generation from source text, gated by the trained AnswerScorer."""
from __future__ import annotations

import random
from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer

from .. import config
from ..answer_scorer import AnswerScorer
from .content_extractor import ContentExtractor, blank_term

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

    def generate(self, text: str, question_count: int, title: str = "") -> dict:
        """Build up to `question_count` cloze MCQs from `text`, keeping only
        questions whose correct answer the AnswerScorer ranks #1 (quality over
        quantity). Returns `{title, description, questions}`."""
        question_count = max(0, question_count)
        result = {
            "title": title or "Quiz",
            "description": f"Generated from {title}" if title else "Generated quiz",
            "questions": [],
        }
        if question_count == 0:
            return result

        candidates = self.extractor.extract_candidates(text, question_count * OVERSAMPLE)
        rng = random.Random(config.RANDOM_SEED)
        questions = []
        for c in candidates:
            distractors = self._distractors(c, candidates)
            if len(distractors) < N_DISTRACTORS:
                continue
            options = [c.term] + distractors[:N_DISTRACTORS]
            stem = blank_term(c.sentence, c.term, BLANK)
            ranked = self.scorer.rank(stem, options, c.sentence)
            if not ranked or ranked[0][0] != c.term:
                continue  # AnswerScorer gate: correct answer must rank #1
            shuffled = list(options)
            rng.shuffle(shuffled)
            questions.append({
                "question_text": stem,
                "question_type": "multiple_choice",
                "options": shuffled,
                "correct_answer": c.term,
                "explanation": c.sentence,
            })
            if len(questions) >= question_count:
                break
        result["questions"] = questions
        return result
