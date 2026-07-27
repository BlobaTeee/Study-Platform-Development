"""Choosing a mock test's paper: weighted toward what the student answers badly."""
import importlib.util
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "quizzes" / "services" / "paper.py")


def _load():
    spec = importlib.util.spec_from_file_location("paper_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


paper = _load()


def _pool(n, source_id=1):
    return [{"id": i, "source_ids": [source_id]} for i in range(1, n + 1)]


# ---- accuracy ---------------------------------------------------------------

def test_accuracy_is_a_percentage_per_source():
    rows = [
        {"source_ids": [1], "is_correct": True},
        {"source_ids": [1], "is_correct": False},
        {"source_ids": [2], "is_correct": True},
    ]
    assert paper.source_accuracy(rows) == {1: 50.0, 2: 100.0}


def test_an_answer_counts_for_every_source_it_came_from():
    rows = [{"source_ids": [1, 2], "is_correct": False}]
    assert paper.source_accuracy(rows) == {1: 0.0, 2: 0.0}


def test_sources_never_answered_are_absent_rather_than_zero():
    # Zero would read as "got it wrong", which is not the same as "not tried".
    assert paper.source_accuracy([]) == {}


# ---- weights ----------------------------------------------------------------

def test_a_weak_source_outweighs_a_strong_one():
    weights = paper.source_weights({1: 30.0, 2: 95.0})
    assert weights[1] > weights[2]


def test_a_middling_source_sits_between_them():
    weights = paper.source_weights({1: 30.0, 2: 70.0, 3: 95.0})
    assert weights[1] > weights[2] > weights[3]


def test_an_unknown_source_weighs_neutral():
    assert paper.question_weight({"source_ids": [99]}, {}) == paper.NEUTRAL_WEIGHT


def test_a_question_takes_the_weight_of_its_weakest_source():
    weights = {1: 1.5, 2: 0.6}
    assert paper.question_weight({"source_ids": [1, 2]}, weights) == 1.5


# ---- sampling ---------------------------------------------------------------

def test_it_returns_exactly_the_requested_count():
    assert len(paper.sample_paper(_pool(30), {}, count=20, seed=1)) == 20


def test_a_pool_smaller_than_the_request_yields_the_whole_pool():
    assert len(paper.sample_paper(_pool(5), {}, count=20, seed=1)) == 5


def test_no_question_appears_twice():
    chosen = paper.sample_paper(_pool(30), {}, count=20, seed=1)
    assert len({entry["id"] for entry in chosen}) == 20


def test_the_same_seed_gives_the_same_paper():
    a = paper.sample_paper(_pool(30), {}, count=10, seed=7)
    b = paper.sample_paper(_pool(30), {}, count=10, seed=7)
    assert [e["id"] for e in a] == [e["id"] for e in b]


def test_different_seeds_give_different_papers():
    a = paper.sample_paper(_pool(40), {}, count=10, seed=1)
    b = paper.sample_paper(_pool(40), {}, count=10, seed=2)
    assert [e["id"] for e in a] != [e["id"] for e in b]


def test_weak_material_is_favoured_over_many_sittings():
    # One weak source, one strong, equal numbers of questions. Over enough
    # papers the weak source should supply clearly more of them — the point of
    # weighting. A single paper proves nothing, so this counts across many.
    pool = ([{"id": i, "source_ids": [1]} for i in range(1, 21)]
            + [{"id": i, "source_ids": [2]} for i in range(21, 41)])
    weights = paper.source_weights({1: 20.0, 2: 95.0})
    weak = 0
    for seed in range(60):
        chosen = paper.sample_paper(pool, weights, count=10, seed=seed)
        weak += sum(1 for e in chosen if e["source_ids"] == [1])
    assert weak > 60 * 10 * 0.5


def test_an_empty_pool_is_an_empty_paper():
    assert paper.sample_paper([], {}, count=10, seed=1) == []


def test_a_zero_or_negative_count_is_an_empty_paper():
    assert paper.sample_paper(_pool(10), {}, count=0, seed=1) == []
    assert paper.sample_paper(_pool(10), {}, count=-5, seed=1) == []
