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


def test_the_handmade_set_flattens_to_one_item_per_attempt():
    from ml_pipeline.step_grading import load
    items = load('handmade')
    assert len(items) == 72
    first = items[0]
    assert first['id'] == 'code-1/0' and first['label'] == -1 and first['subject'] == 'programming'
    assert {i['lang'] for i in items} == {'en', 'vi'}
    assert all(i['label'] == -1 or 0 <= i['label'] <= len(i['steps']) for i in items)


def test_stopping_short_keeps_its_own_label_when_the_set_has_one():
    # The hand-made set labels "stops short" as one past the last step;
    # ProcessBench has no such label, so there it folds into the last step.
    graded = {'verdict': 'needs_work', 'first_wrong_step': 4}
    assert to_label(graded, 3, stops_short=True) == 3
    assert to_label(graded, 3) == 2


def test_each_split_has_its_own_results_file():
    from ml_pipeline.step_grading import results_path
    assert results_path('gsm8k').name == 'step_grading_gsm8k.jsonl'
    assert results_path('handmade').name == 'step_grading_handmade.jsonl'
