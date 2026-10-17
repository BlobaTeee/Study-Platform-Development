"""The arithmetic behind measuring the practice grader on ProcessBench."""
from ml_pipeline.step_grading import balanced_sample, metrics, to_label


def test_a_pass_is_no_error_and_steps_become_zero_based():
    assert to_label({'verdict': 'passed'}, 4) == -1
    assert to_label({'verdict': 'needs_work', 'first_wrong_step': 1}, 4) == 0
    assert to_label({'verdict': 'needs_work', 'first_wrong_step': 3}, 4) == 2


def test_stopping_short_counts_as_the_last_step():
    assert to_label({'verdict': 'needs_work', 'first_wrong_step': 5}, 4) == 3


def test_a_sample_alternates_and_is_the_same_every_run():
    items = [{'id': i, 'label': -1 if i % 3 else 1} for i in range(30)]
    a, b = balanced_sample(items, 8), balanced_sample(items, 8)
    assert [x['id'] for x in a] == [x['id'] for x in b]
    assert [x['label'] == -1 for x in a] == [False, True] * 4


def test_metrics_are_processbenchs():
    gold = [2, 0, -1, -1]
    pred = [2, 1, -1, 0]     # right step; error found but wrong step; right; false alarm
    m = metrics(gold, pred)
    assert m['error_acc'] == 0.5 and m['correct_acc'] == 0.5 and m['f1'] == 0.5
    assert m['detect_acc'] == 0.75


def test_no_items_gives_no_numbers():
    assert metrics([], [])['f1'] is None
