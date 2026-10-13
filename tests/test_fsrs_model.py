"""FSRS-6 memory state, checked against py-fsrs.

The reference numbers come from py-fsrs's own Scheduler (default parameters,
no learning steps, no fuzz) on the same histories, so a change that drifts
from the published model fails here.
"""
from datetime import datetime, timedelta, timezone

import pytest

from ml_pipeline.fsrs_model import AGAIN, EASY, GOOD, RATING, replay, retrievability

T0 = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)


def _state(history):
    return replay([(T0 + timedelta(days=d), r) for d, r in history])


@pytest.mark.parametrize('history, stability, difficulty', [
    ([(0, GOOD)], 2.3065, 2.1181),
    ([(0, GOOD), (3, GOOD)], 13.8269, 2.1112),
    ([(0, GOOD), (10, AGAIN), (11, GOOD)], 2.6272, 7.3823),
    ([(0, EASY), (8, GOOD), (30, GOOD)], 112.7685, 1.0),
    ([(0, AGAIN), (0.2, AGAIN)], 0.0834, 8.8063),
])
def test_memory_state_matches_py_fsrs(history, stability, difficulty):
    state = _state(history)
    assert state.stability == pytest.approx(stability, abs=1e-4)
    assert state.difficulty == pytest.approx(difficulty, abs=1e-4)


def test_recall_is_ninety_percent_after_one_stability_and_falls_after():
    assert retrievability(5, 5) == pytest.approx(0.9)
    assert retrievability(10, 5) == pytest.approx(0.845885, abs=1e-6)
    assert retrievability(0, 5) == pytest.approx(1.0)


def test_the_apps_grades_map_to_ratings():
    assert RATING == {'hard': AGAIN, 'good': GOOD, 'easy': EASY}


def test_no_reviews_means_no_state():
    assert replay([]) is None
