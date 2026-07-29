"""SM-2 scheduling: the pure step behind CardReview.calculate_next_review.

Extracted from the model so the algorithm can be exercised without a database.
It had never run once before now — the app had no self-grading UI, so no review
ever reached it.
"""
import importlib.util
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1] / "backend"


def _load(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, _BACKEND / relative_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sm2 = _load("sm2_under_test", "study_sessions/scheduling.py")
# Loaded alongside sm2 so the agreement test below can compare their grade
# vocabularies without importing insights the normal way (it never survives
# a standalone load through Django's app registry).
ins = _load("insights_for_sm2_check", "analytics/insights.py")


def _step(result, interval=1, ease_factor=2.5, repetitions=0):
    return sm2.next_schedule(result, interval=interval,
                             ease_factor=ease_factor, repetitions=repetitions)


# ---- hard: the card was forgotten or barely recalled ------------------------

def test_hard_restarts_the_card():
    s = _step("hard", interval=21, ease_factor=2.5, repetitions=5)
    assert s.interval == 1
    assert s.repetitions == 0


def test_hard_makes_the_card_harder():
    assert _step("hard", ease_factor=2.5).ease_factor == pytest.approx(2.3)


def test_again_is_no_longer_a_grade():
    assert "again" not in sm2.RESULT_VALUES
    with pytest.raises(ValueError):
        sm2.next_schedule("again", interval=1, ease_factor=2.5, repetitions=0)


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


# ---- easy -------------------------------------------------------------------

def test_easy_makes_the_card_easier_and_stretches_the_interval():
    s = _step("easy", interval=10, ease_factor=2.5, repetitions=3)
    assert s.interval == 25
    assert s.ease_factor == pytest.approx(2.6)


def test_hard_still_resets_further_than_good_advances():
    # However far good would push the card, hard always resets to day one.
    hard = _step("hard", interval=10, ease_factor=2.5, repetitions=3)
    good = _step("good", interval=10, ease_factor=2.5, repetitions=3)
    assert hard.interval < good.interval


@pytest.mark.parametrize("result", ["hard"])
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
    s = sm2.next_schedule("hard", interval=s.interval,
                          ease_factor=s.ease_factor, repetitions=s.repetitions)
    assert s.interval == 1
    assert s.repetitions == 0
    assert s.ease_factor < 2.5


# ---- validation ------------------------------------------------------------

def test_unknown_grade_is_rejected():
    with pytest.raises(ValueError):
        _step("kinda-ok")


def test_all_three_grades_are_accepted():
    for result in sm2.RESULT_VALUES:
        assert _step(result).interval >= 1


# ---- agreement with the analytics side -------------------------------------

def test_insights_and_scheduling_agree_on_what_counts_as_correct():
    assert ins.CORRECT_RESULTS == sm2.CORRECT_RESULTS
    # Every grade the app can record today must be classified by insights.
    assert set(sm2.RESULT_VALUES) <= (ins.CORRECT_RESULTS | ins.INCORRECT_RESULTS)
    # Retired grades stay classified so historical rows keep counting.
    assert sm2.RETIRED_RESULTS <= ins.INCORRECT_RESULTS


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
    # The study page needs the whole card, and is the only caller that should
    # ever see a question's text before it is graded.
    card = {"id": 1, "question": "Q?", "answer": "A", "difficulty": "easy"}
    out = sm2.rank_due_cards([card], {}, TODAY, limit=5)
    assert out[0]["answer"] == "A"
    assert out[0]["difficulty"] == "easy"


# ---- due_counts ------------------------------------------------------------
# What a summary is allowed to know: how much is owed, never which cards.

def test_counts_a_never_studied_card_as_new():
    assert sm2.due_counts([_card(1)], {}, TODAY) == {"due": 0, "overdue": 0, "new": 1}


def test_counts_a_card_scheduled_today_as_due_but_not_overdue():
    assert sm2.due_counts([_card(1)], {1: TODAY}, TODAY) == {
        "due": 1, "overdue": 0, "new": 0
    }


def test_counts_a_late_card_as_both_due_and_overdue():
    # Overdue is a subset of due: it is owed, and it is being forgotten.
    assert sm2.due_counts([_card(1)], {1: TODAY - timedelta(days=2)}, TODAY) == {
        "due": 1, "overdue": 1, "new": 0
    }


def test_counts_ignore_cards_scheduled_ahead():
    assert sm2.due_counts([_card(1)], {1: TODAY + timedelta(days=9)}, TODAY) == {
        "due": 0, "overdue": 0, "new": 0
    }


def test_counts_with_no_cards_are_all_zero():
    assert sm2.due_counts([], {}, TODAY) == {"due": 0, "overdue": 0, "new": 0}


# ---- next_due_batch --------------------------------------------------------
# An empty queue is the algorithm working, but silence makes that look identical
# to a broken one. Saying when cards return is what tells the two apart.

def test_next_due_batch_finds_the_soonest_return():
    schedule = {1: TODAY + timedelta(days=3), 2: TODAY + timedelta(days=1)}
    assert sm2.next_due_batch(schedule, TODAY) == (TODAY + timedelta(days=1), 1)


def test_next_due_batch_counts_everything_returning_that_day():
    soon = TODAY + timedelta(days=1)
    schedule = {1: soon, 2: soon, 3: TODAY + timedelta(days=9)}
    assert sm2.next_due_batch(schedule, TODAY) == (soon, 2)


def test_next_due_batch_ignores_cards_already_owed():
    # Those are due now, not returning later; the queue speaks for them.
    schedule = {1: TODAY, 2: TODAY - timedelta(days=4), 3: TODAY + timedelta(days=2)}
    assert sm2.next_due_batch(schedule, TODAY) == (TODAY + timedelta(days=2), 1)


def test_next_due_batch_reports_nothing_when_no_card_is_scheduled():
    assert sm2.next_due_batch({}, TODAY) == (None, 0)
    assert sm2.next_due_batch({1: TODAY}, TODAY) == (None, 0)


def test_counts_agree_with_the_queue_they_summarise():
    # The number on the summary must match what pressing Study actually gives.
    schedule = {1: TODAY - timedelta(days=2), 2: TODAY, 3: TODAY + timedelta(days=5)}
    cards = [_card(1), _card(2), _card(3), _card(4)]
    counts = sm2.due_counts(cards, schedule, TODAY)
    queue = sm2.rank_due_cards(cards, schedule, TODAY, limit=100)
    assert counts["due"] + counts["new"] == len(queue)


# ---- advance_streak --------------------------------------------------------
# The streak counts consecutive local days with at least one review. Its math
# is pure here so it can be tested without a database; the model delegates to it.

def test_first_ever_review_starts_a_streak_of_one():
    s = sm2.advance_streak(current=0, best=0, last_date=None, today=TODAY)
    assert (s.current, s.best, s.last_date) == (1, 1, TODAY)


def test_a_second_review_the_same_day_changes_nothing():
    s = sm2.advance_streak(current=3, best=5, last_date=TODAY, today=TODAY)
    assert (s.current, s.best, s.last_date) == (3, 5, TODAY)


def test_a_review_the_next_day_extends_the_streak():
    s = sm2.advance_streak(current=3, best=5, last_date=TODAY, today=TODAY + timedelta(days=1))
    assert s.current == 4
    assert s.last_date == TODAY + timedelta(days=1)


def test_extending_past_the_record_raises_the_best():
    s = sm2.advance_streak(current=5, best=5, last_date=TODAY, today=TODAY + timedelta(days=1))
    assert s.current == 6
    assert s.best == 6


def test_a_gap_of_two_days_restarts_the_streak():
    s = sm2.advance_streak(current=9, best=9, last_date=TODAY, today=TODAY + timedelta(days=2))
    assert s.current == 1
    assert s.best == 9  # the record survives a broken streak
    assert s.last_date == TODAY + timedelta(days=2)
