"""SM-2 scheduling: the pure step behind CardReview.calculate_next_review.

Extracted from the model so the algorithm can be exercised without a database.
It had never run once before now — the app had no self-grading UI, so no review
ever reached it.
"""
import importlib.util
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "study_sessions" / "scheduling.py")


def _load():
    spec = importlib.util.spec_from_file_location("sm2_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sm2 = _load()


def _step(result, interval=1, ease_factor=2.5, repetitions=0):
    return sm2.next_schedule(result, interval=interval,
                             ease_factor=ease_factor, repetitions=repetitions)


# ---- again: the card was forgotten -----------------------------------------

def test_again_restarts_the_card():
    s = _step("again", interval=21, ease_factor=2.5, repetitions=5)
    assert s.repetitions == 0
    assert s.interval == 1


def test_again_makes_the_card_harder():
    assert _step("again", ease_factor=2.5).ease_factor == pytest.approx(2.3)


# ---- good: the normal path -------------------------------------------------

def test_first_good_review_comes_back_tomorrow():
    assert _step("good", repetitions=0).interval == 1


def test_second_good_review_comes_back_in_three_days():
    assert _step("good", interval=1, repetitions=1).interval == 3


def test_later_good_reviews_scale_by_ease():
    assert _step("good", interval=3, ease_factor=2.5, repetitions=2).interval == 7


def test_good_leaves_ease_alone():
    s = _step("good", ease_factor=2.5, repetitions=2)
    assert s.ease_factor == pytest.approx(2.5)


# ---- easy / hard -----------------------------------------------------------

def test_easy_makes_the_card_easier_and_stretches_the_interval():
    s = _step("easy", interval=10, ease_factor=2.5, repetitions=3)
    assert s.interval == 25
    assert s.ease_factor == pytest.approx(2.6)


def test_hard_stretches_only_slightly_and_lowers_ease():
    s = _step("hard", interval=10, ease_factor=2.5, repetitions=3)
    assert s.interval == 12
    assert s.ease_factor == pytest.approx(2.35)


def test_hard_never_collapses_the_interval_below_a_day():
    assert _step("hard", interval=1).interval == 1


@pytest.mark.parametrize("result", ["again", "hard"])
def test_ease_never_falls_below_the_floor(result):
    assert _step(result, ease_factor=1.3).ease_factor == pytest.approx(sm2.MIN_EASE_FACTOR)


# ---- carrying state forward ------------------------------------------------

def test_repeated_good_reviews_lengthen_the_gap():
    # Each review builds on the last. If state were not carried forward, every
    # review would restart at repetitions=1 and the interval would never grow.
    s = sm2.INITIAL
    intervals = []
    for _ in range(4):
        s = sm2.next_schedule("good", interval=s.interval,
                              ease_factor=s.ease_factor, repetitions=s.repetitions)
        intervals.append(s.interval)
    assert intervals == [1, 3, 7, 17]


def test_forgetting_undoes_the_progress():
    s = _step("good", interval=17, ease_factor=2.5, repetitions=4)
    s = sm2.next_schedule("again", interval=s.interval,
                          ease_factor=s.ease_factor, repetitions=s.repetitions)
    assert s.interval == 1
    assert s.repetitions == 0
    assert s.ease_factor < 2.5


# ---- validation ------------------------------------------------------------

def test_unknown_grade_is_rejected():
    with pytest.raises(ValueError):
        _step("kinda-ok")


def test_all_four_grades_are_accepted():
    for result in sm2.RESULT_VALUES:
        assert _step(result).interval >= 1


# ---- agreement with the analytics side -------------------------------------

def _load_insights():
    path = Path(__file__).resolve().parents[1] / "backend" / "analytics" / "insights.py"
    spec = importlib.util.spec_from_file_location("insights_for_sm2_check", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_analytics_grades_the_same_way_the_scheduler_does():
    # Both modules are loaded standalone and so keep their own copy of the
    # vocabulary. If they drift, accuracy stops matching the schedule.
    ins = _load_insights()
    assert ins.CORRECT_RESULTS == sm2.CORRECT_RESULTS
    assert ins.CORRECT_RESULTS | ins.INCORRECT_RESULTS == set(sm2.RESULT_VALUES)


# ---- latest_schedule -------------------------------------------------------
# A card's schedule lives on its most recent review; older rows are history.

TODAY = date(2026, 7, 16)


def _row(card_id, next_review_date, reviewed_at):
    return {"flashcard_id": card_id, "next_review_date": next_review_date,
            "review_date": reviewed_at}


def test_latest_schedule_takes_the_most_recent_review():
    rows = [_row(1, date(2026, 7, 17), datetime(2026, 7, 10, 9, 0)),
            _row(1, date(2026, 8, 1), datetime(2026, 7, 15, 9, 0))]
    assert sm2.latest_schedule(rows) == {1: date(2026, 8, 1)}


def test_latest_schedule_does_not_depend_on_row_order():
    newest = _row(1, date(2026, 8, 1), datetime(2026, 7, 15, 9, 0))
    oldest = _row(1, date(2026, 7, 17), datetime(2026, 7, 10, 9, 0))
    assert sm2.latest_schedule([newest, oldest]) == sm2.latest_schedule([oldest, newest])


def test_latest_schedule_keeps_cards_apart():
    rows = [_row(1, date(2026, 7, 17), datetime(2026, 7, 15, 9, 0)),
            _row(2, date(2026, 9, 1), datetime(2026, 7, 15, 9, 0))]
    assert sm2.latest_schedule(rows) == {1: date(2026, 7, 17), 2: date(2026, 9, 1)}


def test_latest_schedule_of_no_reviews_is_empty():
    assert sm2.latest_schedule([]) == {}


# ---- rank_due_cards --------------------------------------------------------

def _card(cid, question="Q?"):
    return {"id": cid, "question": question}


def test_a_card_scheduled_for_the_future_is_not_due():
    # The whole point of spaced repetition: do not study what you still know.
    out = sm2.rank_due_cards([_card(1)], {1: TODAY + timedelta(days=17)}, TODAY, limit=5)
    assert out == []


def test_a_card_scheduled_for_today_is_due():
    out = sm2.rank_due_cards([_card(1)], {1: TODAY}, TODAY, limit=5)
    assert out[0]["status"] == sm2.STATUS_DUE
    assert out[0]["overdue_days"] == 0


def test_an_overdue_card_reports_how_late_it_is():
    out = sm2.rank_due_cards([_card(1)], {1: TODAY - timedelta(days=3)}, TODAY, limit=5)
    assert out[0]["overdue_days"] == 3


def test_a_never_studied_card_is_new():
    out = sm2.rank_due_cards([_card(1)], {}, TODAY, limit=5)
    assert out[0]["status"] == sm2.STATUS_NEW
    assert out[0]["overdue_days"] == 0


def test_most_overdue_card_comes_first():
    schedule = {1: TODAY - timedelta(days=1), 2: TODAY - timedelta(days=9)}
    out = sm2.rank_due_cards([_card(1), _card(2)], schedule, TODAY, limit=5)
    assert [c["id"] for c in out] == [2, 1]


def test_cards_at_risk_come_before_cards_never_seen():
    # An overdue card is being forgotten now; a new card is only an opportunity.
    out = sm2.rank_due_cards([_card(1), _card(2)], {2: TODAY}, TODAY, limit=5)
    assert [c["id"] for c in out] == [2, 1]
    assert out[1]["status"] == sm2.STATUS_NEW


def test_due_ranking_respects_the_limit():
    cards = [_card(i) for i in range(1, 6)]
    assert len(sm2.rank_due_cards(cards, {}, TODAY, limit=2)) == 2


def test_due_ranking_is_deterministic_on_ties():
    out = sm2.rank_due_cards([_card(3), _card(1), _card(2)], {}, TODAY, limit=5)
    assert [c["id"] for c in out] == [1, 2, 3]


def test_due_ranking_keeps_the_callers_card_fields():
    # The study page needs the whole card; analytics passes only id + question.
    card = {"id": 1, "question": "Q?", "answer": "A", "difficulty": "easy"}
    out = sm2.rank_due_cards([card], {}, TODAY, limit=5)
    assert out[0]["answer"] == "A"
    assert out[0]["difficulty"] == "easy"
