"""The trained answer scorer: correct-answer vs. distractor."""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from . import config
from .features.answer_features import FeatureBuilder


class AnswerScorer:
    """Bundles a fitted TF-IDF feature builder + scaler + classifier."""

    def __init__(self, classifier=None):
        self.classifier = classifier or LogisticRegression(
            class_weight="balanced", max_iter=1000,
            random_state=config.RANDOM_SEED)
        self.feature_builder = FeatureBuilder()
        self.scaler = StandardScaler()

    def fit(self, train_long_df: pd.DataFrame) -> "AnswerScorer":
        self.feature_builder.fit(train_long_df)
        X = self.scaler.fit_transform(self.feature_builder.transform(train_long_df))
        self.classifier.fit(X, train_long_df["is_correct"].to_numpy())
        return self

    def _proba(self, X: np.ndarray) -> np.ndarray:
        if hasattr(self.classifier, "predict_proba"):
            return self.classifier.predict_proba(X)[:, 1]
        scores = self.classifier.decision_function(X)  # LinearSVC fallback
        return 1.0 / (1.0 + np.exp(-scores))

    def predict_proba(self, long_df: pd.DataFrame) -> np.ndarray:
        X = self.scaler.transform(self.feature_builder.transform(long_df))
        return self._proba(X)

    def score(self, question: str, candidate: str, support: str) -> float:
        df = pd.DataFrame([{"question": question, "candidate": candidate,
                            "support": support}])
        return float(self.predict_proba(df)[0])

    def rank(self, question, candidates, support):
        df = pd.DataFrame([{"question": question, "candidate": c,
                            "support": support} for c in candidates])
        probs = self.predict_proba(df)
        return sorted(zip(candidates, (float(p) for p in probs)),
                      key=lambda t: t[1], reverse=True)

    def save(self, path) -> None:
        config.ensure_dirs()
        joblib.dump(self, Path(path))

    @classmethod
    def load(cls, path) -> "AnswerScorer":
        return joblib.load(Path(path))
