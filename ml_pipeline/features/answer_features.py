"""Expand SciQ rows into (question, candidate) examples and build features."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import HashingVectorizer, TfidfVectorizer

from .. import config

_DISTRACTORS = ["distractor1", "distractor2", "distractor3"]


def expand_candidates(sciq_df: pd.DataFrame, shuffle: bool = True) -> pd.DataFrame:
    """One row per candidate answer; is_correct=1 for the correct answer.

    Candidates are shuffled within each question (seeded) so that answer
    position carries no information — otherwise a tie in ranking scores would
    leak the label via the correct answer's fixed position.
    """
    rng = np.random.RandomState(config.RANDOM_SEED)
    records = []
    for qid, row in enumerate(sciq_df.itertuples(index=False)):
        base = {"question_id": qid, "question": row.question,
                "support": row.support, "split": row.split}
        group = [{**base, "candidate": row.correct_answer, "is_correct": 1}]
        for col in _DISTRACTORS:
            group.append({**base, "candidate": getattr(row, col), "is_correct": 0})
        if shuffle:
            rng.shuffle(group)
        records.extend(group)
    return pd.DataFrame.from_records(records)


def _tokens(text: str) -> set:
    return set(str(text).lower().split())


def token_overlap(candidate: str, context: str) -> float:
    """Fraction of candidate tokens that also appear in the context."""
    cand = _tokens(candidate)
    if not cand:
        return 0.0
    return len(cand & _tokens(context)) / len(cand)


# Backwards-compatible private alias used internally by FeatureBuilder.
_overlap = token_overlap


def _row_cosine(a_vecs, b_vecs) -> np.ndarray:
    """Row-wise cosine similarity between two aligned sparse TF-IDF matrices."""
    num = np.asarray(a_vecs.multiply(b_vecs).sum(axis=1)).ravel()
    na = np.sqrt(np.asarray(a_vecs.multiply(a_vecs).sum(axis=1)).ravel())
    nb = np.sqrt(np.asarray(b_vecs.multiply(b_vecs).sum(axis=1)).ravel())
    denom = na * nb
    return np.divide(num, denom, out=np.zeros_like(num), where=denom > 0)


class FeatureBuilder:
    """Builds an engineered dense feature matrix for candidate answers."""

    FEATURE_NAMES = [
        "cand_support_cos", "cand_question_cos",
        "cand_support_overlap", "cand_question_overlap",
        "cand_len_tokens", "cand_len_chars",
        "cand_is_numeric", "support_len_tokens",
    ]

    def __init__(self, analyzer: str = "word"):
        # "word": a word vocabulary learnt from the training text (the original
        # model). "char": character 3-5-grams within words, so a term the
        # training text never had (e.g. "injection" after school science) still
        # matches itself in the support. Chosen in notebooks/11_answer_scorer_domains.
        self.analyzer = analyzer
        self.vectorizer: TfidfVectorizer | HashingVectorizer | None = None

    def fit(self, long_df: pd.DataFrame) -> "FeatureBuilder":
        corpus = pd.concat([long_df["support"], long_df["question"]]).astype(str)
        if getattr(self, "analyzer", "word") == "char":
            # Hashed, not fitted: a learnt vocabulary of character n-grams would
            # still miss the n-grams of words the training text never had.
            self.vectorizer = HashingVectorizer(
                analyzer="char_wb", ngram_range=(3, 5), n_features=2 ** 20,
                alternate_sign=False, norm="l2", lowercase=True,
            )
        else:
            self.vectorizer = TfidfVectorizer(
                max_features=config.TFIDF_MAX_FEATURES,
                ngram_range=config.TFIDF_NGRAM,
                stop_words="english",
            ).fit(corpus)
        return self

    def transform(self, long_df: pd.DataFrame) -> np.ndarray:
        if self.vectorizer is None:
            raise RuntimeError("FeatureBuilder.transform called before fit")
        cand = long_df["candidate"].astype(str)
        support = long_df["support"].astype(str)
        question = long_df["question"].astype(str)

        cv, sv, qv = (self.vectorizer.transform(x) for x in (cand, support, question))
        cand_support_cos = _row_cosine(cv, sv)
        cand_question_cos = _row_cosine(cv, qv)

        cand_support_overlap = np.array(
            [_overlap(c, s) for c, s in zip(cand, support)])
        cand_question_overlap = np.array(
            [_overlap(c, q) for c, q in zip(cand, question)])
        cand_len_tokens = cand.str.split().str.len().to_numpy(dtype=float)
        cand_len_chars = cand.str.len().to_numpy(dtype=float)
        cand_is_numeric = cand.str.replace(".", "", regex=False).str.strip().str.isdigit().to_numpy(dtype=float)
        support_len_tokens = support.str.split().str.len().to_numpy(dtype=float)

        return np.column_stack([
            cand_support_cos, cand_question_cos,
            cand_support_overlap, cand_question_overlap,
            cand_len_tokens, cand_len_chars,
            cand_is_numeric, support_len_tokens,
        ])
