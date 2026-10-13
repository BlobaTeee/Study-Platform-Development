"""Half-life regression: how likely a card is still remembered after a gap."""
import math
import random

import pytest

from ml_pipeline.memory_model import (
    MAX_HALF_LIFE_DAYS, MIN_HALF_LIFE_DAYS, MemoryModel, fit, half_life, recall_probability,
)

MODEL = MemoryModel(weights={'right': 1.2, 'wrong': -0.6, 'bias': 0.5})


def test_more_right_answers_mean_a_longer_half_life():
    assert half_life(MODEL, right=5, wrong=0) > half_life(MODEL, right=1, wrong=0)


def test_more_wrong_answers_mean_a_shorter_half_life():
    assert half_life(MODEL, right=3, wrong=3) < half_life(MODEL, right=3, wrong=0)


def test_recall_halves_after_one_half_life_and_keeps_falling():
    h = half_life(MODEL, right=2, wrong=1)
    assert recall_probability(MODEL, h, right=2, wrong=1) == pytest.approx(0.5, abs=1e-6)
    assert recall_probability(MODEL, 2 * h, right=2, wrong=1) < 0.5
    assert recall_probability(MODEL, 0, right=2, wrong=1) > 0.99


def test_half_life_stays_within_bounds():
    huge = MemoryModel(weights={'right': 50.0, 'wrong': 0.0, 'bias': 0.0})
    tiny = MemoryModel(weights={'right': 0.0, 'wrong': 0.0, 'bias': -50.0})
    assert half_life(huge, 100, 0) == MAX_HALF_LIFE_DAYS
    assert half_life(tiny, 0, 0) == MIN_HALF_LIFE_DAYS


def test_fitting_recovers_the_direction_of_the_true_weights():
    rng = random.Random(7)
    truth = MemoryModel(weights={'right': 1.0, 'wrong': -0.8, 'bias': 1.0})
    rows = []
    for _ in range(4000):
        right, wrong = rng.randint(0, 8), rng.randint(0, 4)
        delta = rng.uniform(0.05, 20)
        rows.append((delta, right, wrong, recall_probability(truth, delta, right, wrong)))

    model = fit(rows)

    assert model.weights['right'] > 0 > model.weights['wrong']
    errors = [abs(recall_probability(model, d, r, w) - p) for d, r, w, p in rows]
    assert sum(errors) / len(errors) < 0.08


def test_a_model_survives_a_round_trip(tmp_path):
    path = tmp_path / 'model.json'
    MODEL.save(path)
    assert MemoryModel.load(path).weights == MODEL.weights


def test_a_wrong_answer_never_lengthens_memory_even_when_the_data_say_so():
    # In Duolingo's traces more wrong answers come with more exposure, so an
    # unconstrained fit learns "wrong answers lengthen memory". The fitted
    # weights are held to the right signs.
    rng = random.Random(3)
    exposure_heavy = MemoryModel(weights={'right': 0.6, 'wrong': 0.5, 'bias': 1.0})
    rows = []
    for _ in range(3000):
        right, wrong = rng.randint(0, 8), rng.randint(0, 4)
        delta = rng.uniform(0.05, 20)
        rows.append((delta, right, wrong, recall_probability(exposure_heavy, delta, right, wrong)))

    model = fit(rows)

    assert model.weights['right'] >= 0
    assert model.weights['wrong'] <= 0
