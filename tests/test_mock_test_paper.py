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


def test_the_same_seed_gives_the_same_paper_regardless_of_pool_order():
    # The draw is keyed by id (via the sort in sample_paper), not by position,
    # because the next task's pool comes from a Django queryset — and without
    # an explicit ORDER BY, Postgres does not promise the same row order
    # between calls. If the draw depended on position, the same seed over a
    # reordered pool would silently pick a different set of ids.
    forward = _pool(30)
    reversed_pool = list(reversed(forward))
    a = paper.sample_paper(forward, {}, count=10, seed=7)
    b = paper.sample_paper(reversed_pool, {}, count=10, seed=7)
    assert {e["id"] for e in a} == {e["id"] for e in b}


def test_duplicate_ids_in_the_pool_are_collapsed_to_one():
    # The next task's pool is built by matching questions to a notebook's
    # documents, which can yield two entries for the same question (one row
    # per matching source). MockTestQuestion's unique_together on
    # (mock_test, question) would turn an undetected duplicate into an
    # IntegrityError far from its cause, so sample_paper must dedupe first.
    pool = [{"id": 1, "source_ids": [1]}, {"id": 1, "source_ids": [1]},
            {"id": 2, "source_ids": [1]}]
    chosen = paper.sample_paper(pool, {}, count=10, seed=1)
    ids = [e["id"] for e in chosen]
    assert ids.count(1) <= 1
    assert set(ids) == {1, 2}


def test_weak_material_is_favoured_over_many_sittings():
    # One weak source, one strong, equal numbers of questions in the pool.
    # A single paper proves nothing (uniform sampling would too, roughly half
    # the time), so this compares the real weights against uniform weights
    # ({}) over the same seeds and the same pool. Only the weighting differs
    # between the two runs, so a clear gap can only come from the weighting.
    #
    # Observed with this pool/seed range: weighted 413, uniform 290 (out of
    # 600 total draws), a margin of 123. The threshold below (80) sits well
    # inside that margin and well outside the noise a broken implementation
    # could produce, so an implementation with the weighting removed (weights
    # treated as uniform) would fail it, while the real weighting passes with
    # room to spare.
    pool = ([{"id": i, "source_ids": [1]} for i in range(1, 21)]
            + [{"id": i, "source_ids": [2]} for i in range(21, 41)])
    weights = paper.source_weights({1: 20.0, 2: 95.0})

    def weak_count(w):
        total = 0
        for seed in range(60):
            chosen = paper.sample_paper(pool, w, count=10, seed=seed)
            total += sum(1 for e in chosen if e["source_ids"] == [1])
        return total

    weighted = weak_count(weights)
    uniform = weak_count({})
    assert weighted - uniform > 80


def test_an_empty_pool_is_an_empty_paper():
    assert paper.sample_paper([], {}, count=10, seed=1) == []


def test_a_zero_or_negative_count_is_an_empty_paper():
    assert paper.sample_paper(_pool(10), {}, count=0, seed=1) == []
    assert paper.sample_paper(_pool(10), {}, count=-5, seed=1) == []


# ---- clamp_int ----------------------------------------------------------

def test_clamp_int_returns_the_default_when_value_is_none():
    assert paper.clamp_int(None, 5, 50, default=20) == 20


def test_clamp_int_clamps_below_the_floor():
    assert paper.clamp_int(1, 5, 50, default=20) == 5
    assert paper.clamp_int("-100", 5, 50, default=20) == 5


def test_clamp_int_clamps_above_the_ceiling():
    assert paper.clamp_int(9999, 5, 50, default=20) == 50
    assert paper.clamp_int("500", 5, 50, default=20) == 50


def test_clamp_int_returns_an_in_range_value_unchanged():
    assert paper.clamp_int(30, 5, 50, default=20) == 30
    assert paper.clamp_int("30", 5, 50, default=20) == 30


def test_clamp_int_accepts_a_whole_valued_float():
    # JSON has no separate integer type, so a body decoded from JSON may hand
    # back 20.0 for a field a form would have sent as "20".
    assert paper.clamp_int(20.0, 5, 50, default=20) == 20


def test_clamp_int_rejects_non_numeric_text():
    import pytest
    with pytest.raises(ValueError):
        paper.clamp_int("abc", 5, 50, default=20)


def test_clamp_int_rejects_none_like_junk():
    import pytest
    with pytest.raises(ValueError):
        paper.clamp_int("None", 5, 50, default=20)
    with pytest.raises(ValueError):
        paper.clamp_int("null", 5, 50, default=20)


def test_clamp_int_rejects_a_fractional_value():
    import pytest
    with pytest.raises(ValueError):
        paper.clamp_int(3.5, 5, 50, default=20)
    with pytest.raises(ValueError):
        paper.clamp_int("3.5", 5, 50, default=20)


def test_clamp_int_rejects_a_bool():
    # bool is a subclass of int in Python, so without an explicit check
    # isinstance(True, int) would quietly let True become 1.
    import pytest
    with pytest.raises(ValueError):
        paper.clamp_int(True, 5, 50, default=20)
