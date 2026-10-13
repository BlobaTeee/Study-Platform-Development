"""How likely a card is still remembered after a gap: half-life regression.

Settles & Meeder (2016), "A Trainable Spaced Repetition Model for Language
Learning", ACL. Memory of an item decays exponentially, p = 2^(-delta / h),
and its half-life h grows with what the learner got right and shrinks with
what they got wrong: h = 2^(w . x), with x = (sqrt(1 + right),
sqrt(1 + wrong), 1). The weights are fitted on Duolingo's public learning
traces in notebooks/08_memory_forecast.ipynb and kept in
models/memory_hlr.json, as an experiment: on that data it overrates recall
for flashcards, and the app forecasts with FSRS (fsrs_model.py) instead.

The lexeme features of the paper are left out on purpose: a model of
Spanish words has nothing to say about a student's own flashcards, while how
history shapes forgetting carries over.

No Django imports; the arithmetic is unit-testable on its own.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

MIN_HALF_LIFE_DAYS = 15.0 / (24 * 60)      # fifteen minutes
MAX_HALF_LIFE_DAYS = 274.0                 # about nine months
MIN_P, MAX_P = 0.0001, 0.9999
LN2 = math.log(2.0)


@dataclass
class MemoryModel:
    weights: dict[str, float] = field(default_factory=lambda: {'right': 0.0, 'wrong': 0.0, 'bias': 0.0})

    def save(self, path) -> None:
        Path(path).write_text(json.dumps({'weights': self.weights}, indent=2))

    @classmethod
    def load(cls, path) -> 'MemoryModel':
        return cls(weights=json.loads(Path(path).read_text())['weights'])


def features(right: int, wrong: int) -> dict[str, float]:
    return {'right': math.sqrt(1 + right), 'wrong': math.sqrt(1 + wrong), 'bias': 1.0}


def half_life(model: MemoryModel, right: int, wrong: int) -> float:
    """Days until recall falls to one half."""
    dot = sum(model.weights.get(k, 0.0) * v for k, v in features(right, wrong).items())
    try:
        h = 2.0 ** dot
    except OverflowError:
        h = MAX_HALF_LIFE_DAYS
    return min(max(h, MIN_HALF_LIFE_DAYS), MAX_HALF_LIFE_DAYS)


def recall_probability(model: MemoryModel, delta_days: float, right: int, wrong: int) -> float:
    p = 2.0 ** (-max(delta_days, 0.0) / half_life(model, right, wrong))
    return min(max(p, MIN_P), MAX_P)


def fit(rows: Iterable[tuple[float, int, int, float]], *, half_life_weight: float = 0.0,
        l2: float = 0.0, signed: bool = True) -> MemoryModel:
    """Fit the weights on (delta_days, right, wrong, p_recall) rows.

    The paper's loss, (p - p^)^2 + alpha (h - h^)^2 + l2 |w|^2 with the
    observed half-life h = -delta / log2(p), with one change: the half-life
    term is taken on a log2 scale. In days it reaches 274 and its square
    swamps the recall term entirely; on a log scale both stay comparable.
    Minimised over the whole batch with L-BFGS rather than the paper's SGD:
    on a few hundred thousand rows SGD left the "wrong" weight unseparated
    from the bias, since the two features move almost together.

    The weights are held to their signs: a right answer never shortens
    memory and a wrong one never lengthens it. Unconstrained, Duolingo's
    traces teach the opposite for wrong answers, because there more wrong
    answers come with more exposure; carried into the app, marking a card
    Hard would then make it look better remembered. Defaults for the two
    penalties were chosen on a validation split in notebook 08.
    """
    import numpy as np
    from scipy.optimize import minimize

    data = np.array(list(rows), dtype=float)
    if data.size == 0:
        return MemoryModel()
    delta, right, wrong, p = data.T
    p = np.clip(p, MIN_P, MAX_P)
    x = np.stack([np.sqrt(1 + right), np.sqrt(1 + wrong), np.ones_like(right)], axis=1)
    log_h_obs = np.log2(np.clip(-delta / np.log2(p), MIN_HALF_LIFE_DAYS, MAX_HALF_LIFE_DAYS))
    lo, hi = math.log2(MIN_HALF_LIFE_DAYS), math.log2(MAX_HALF_LIFE_DAYS)

    def loss(w):
        log_h = np.clip(x @ w, lo, hi)
        p_hat = np.clip(2.0 ** (-delta / 2.0 ** log_h), MIN_P, MAX_P)
        return (np.mean((p_hat - p) ** 2)
                + half_life_weight * np.mean((log_h - log_h_obs) ** 2)
                + l2 * float(w @ w))

    bounds = [(0.0, None), (None, 0.0), (None, None)] if signed else None   # right, wrong, bias
    best = minimize(loss, np.zeros(3), method='L-BFGS-B', bounds=bounds)
    return MemoryModel(weights={k: float(v) for k, v in zip(('right', 'wrong', 'bias'), best.x)})
