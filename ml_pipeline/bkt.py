"""Bayesian Knowledge Tracing: how likely a student knows a concept, from the
order in which they answered questions on it.

Corbett & Anderson (1995). A concept is known or not; each answer is right
with probability 1 - slip if known and guess if not; after each answer the
student may learn it (learn). Guessing a four-option question is easier
than guessing a written answer, so the two kinds get their own guess. The
parameters are fitted on ASSISTments 2009 in notebooks/10_knowledge_map.ipynb
and kept in models/bkt.json. No Django imports.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

PATH = Path(__file__).resolve().parent / 'models' / 'bkt.json'
CHOICE_TYPES = {'choose_1', 'choose_n', 'choice'}
BOUNDS = {'init': (0.01, 0.99), 'learn': (0.01, 0.6), 'slip': (0.01, 0.3),
          'guess_choice': (0.01, 0.5), 'guess_written': (0.01, 0.3)}
EPS = 1e-6


@dataclass(frozen=True)
class Params:
    init: float
    learn: float
    slip: float
    guess_choice: float
    guess_written: float

    def guess(self, kind: str) -> float:
        return self.guess_choice if kind == 'choice' else self.guess_written


def kind_of(answer_type: str) -> str:
    return 'choice' if answer_type in CHOICE_TYPES else 'written'


def p_correct(p_known: float, kind: str, params: Params) -> float:
    return p_known * (1 - params.slip) + (1 - p_known) * params.guess(kind)


def update(p_known: float, correct: bool, kind: str, params: Params) -> float:
    g, s = params.guess(kind), params.slip
    if correct:
        post = p_known * (1 - s) / max(EPS, p_known * (1 - s) + (1 - p_known) * g)
    else:
        post = p_known * s / max(EPS, p_known * s + (1 - p_known) * (1 - g))
    return post + (1 - post) * params.learn


def trace(events, params: Params) -> float:
    p = params.init
    for correct, kind in events:
        p = update(p, bool(correct), kind, params)
    return p


def neg_log_likelihood(sequences, params: Params) -> float:
    total = 0.0
    for seq in sequences:
        p = params.init
        for correct, kind in seq:
            q = min(1 - EPS, max(EPS, p_correct(p, kind, params)))
            total -= math.log(q if correct else 1 - q)
            p = update(p, correct, kind, params)
    return total


def fit(sequences) -> Params:
    from scipy.optimize import minimize
    names = list(BOUNDS)
    start = [0.3, 0.15, 0.1, 0.25, 0.1]
    res = minimize(lambda x: neg_log_likelihood(sequences, Params(*x)), start, method='L-BFGS-B',
                   bounds=[BOUNDS[n] for n in names])
    return Params(*[float(v) for v in res.x])


def save(params: Params, thresholds: dict, path: Path = PATH, **extra) -> None:
    path.write_text(json.dumps({'params': asdict(params), 'thresholds': thresholds, **extra}, indent=1) + '\n')


def load(path: Path = PATH) -> tuple[Params, dict]:
    doc = json.loads(path.read_text())
    return Params(**doc['params']), doc['thresholds']
