"""Measuring the practice grader on ProcessBench.

ProcessBench (Zheng et al. 2024, Qwen, Apache-2.0) gives solutions split into
steps with the index of the earliest wrong step, labelled by experts, or -1
when every step is right. That is what Submit reports, so the grader can be
scored on it directly.

The app grades against a rubric written with the problem; ProcessBench has
none, so each problem goes through the same path as a student's own problem
(rubric first, then the grade). The model calls run in the backend
(`manage.py eval_step_grading`), which appends one line per item to a JSONL
file; this module reads that file and does the arithmetic, with no Django.

Metrics are ProcessBench's: accuracy on the erroneous solutions (the exact
first wrong step), accuracy on the correct ones (no error reported), and
their harmonic mean.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'datasets' / 'raw' / 'ProcessBench'
# Kept with the other reports (committed): each line cost two model requests.
RESULTS = Path(__file__).resolve().parent / 'reports' / 'step_grading_gsm8k.jsonl'


def load(split: str = 'gsm8k') -> list[dict]:
    return json.loads((DATA / f'{split}.json').read_text())


def balanced_sample(items: list[dict], n: int, seed: int = 7) -> list[dict]:
    """`n` items, half with an error and half without, in a fixed order, so a
    run stopped by the daily quota resumes on the same items."""
    rng = random.Random(seed)
    wrong = [i for i in items if i['label'] != -1]
    right = [i for i in items if i['label'] == -1]
    rng.shuffle(wrong)
    rng.shuffle(right)
    out = []
    for a, b in zip(wrong, right):
        out += [a, b]
    return out[:n]


def to_label(result: dict, n_steps: int) -> int:
    """The app's grade in ProcessBench's terms: a 0-based step, or -1.

    "Stops short" (a step past the last) has no ProcessBench label; the last
    step is where the attempt went wrong, so it counts as that one."""
    if result.get('verdict') == 'passed':
        return -1
    step = result.get('first_wrong_step')
    if not isinstance(step, int) or step < 1:
        return 0
    return min(step, n_steps) - 1


def metrics(gold: list[int], pred: list[int]) -> dict:
    wrong = [(g, p) for g, p in zip(gold, pred) if g != -1]
    right = [(g, p) for g, p in zip(gold, pred) if g == -1]
    error_acc = sum(g == p for g, p in wrong) / len(wrong) if wrong else None
    correct_acc = sum(p == -1 for _, p in right) / len(right) if right else None
    # Whether an error was flagged at all, wherever it was put.
    detect = sum((g == -1) == (p == -1) for g, p in zip(gold, pred)) / len(gold) if gold else None
    f1 = (2 * error_acc * correct_acc / (error_acc + correct_acc)
          if error_acc is not None and correct_acc and error_acc + correct_acc else None)
    return {'n': len(gold), 'n_with_error': len(wrong), 'error_acc': error_acc,
            'correct_acc': correct_acc, 'f1': f1, 'detect_acc': detect}


def read_results(path: Path = RESULTS) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
