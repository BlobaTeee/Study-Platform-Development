"""Expand SciQ rows into (question, candidate) examples and build features."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from .. import config

_DISTRACTORS = ["distractor1", "distractor2", "distractor3"]


def expand_candidates(sciq_df: pd.DataFrame) -> pd.DataFrame:
    """One row per candidate answer; is_correct=1 for the correct answer."""
    records = []
    for qid, row in enumerate(sciq_df.itertuples(index=False)):
        base = {"question_id": qid, "question": row.question,
                "support": row.support, "split": row.split}
        records.append({**base, "candidate": row.correct_answer, "is_correct": 1})
        for col in _DISTRACTORS:
            records.append({**base, "candidate": getattr(row, col), "is_correct": 0})
    return pd.DataFrame.from_records(records)


def _tokens(text: str) -> set:
    return set(str(text).lower().split())


def _overlap(candidate: str, context: str) -> float:
    cand = _tokens(candidate)
    if not cand:
        return 0.0
    return len(cand & _tokens(context)) / len(cand)


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

    def __init__(self):
        self.vectorizer: TfidfVectorizer | None = None

    def fit(self, long_df: pd.DataFrame) -> "FeatureBuilder":
        corpus = pd.concat([long_df["support"], long_df["question"]]).astype(str)
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
