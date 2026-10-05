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
    # Good would give 10 x 2.5 = 25 days; easy goes a step further (x1.3).
    s = _step("easy", interval=10, ease_factor=2.5, repetitions=3)
    assert s.interval == 32
    assert s.ease_factor == pytest.approx(2.6)


def test_a_first_review_marked_easy_waits_four_days():
    assert _step("easy", repetitions=0).interval == 4


@pytest.mark.parametrize("repetitions", [0, 1, 2, 3, 5])
@pytest.mark.parametrize("interval", [1, 2, 3, 4, 7, 10, 30])
@pytest.mark.parametrize("ease", [1.3, 1.8, 2.5, 2.8])
def test_easy_never_comes_back_sooner_than_good(repetitions, interval, ease):
    # It did: on a second review good jumped to its fixed 3 days while easy
    # multiplied the 1-day gap, so "very easy" returned in 2 — sooner. A
    # learner who marks most cards easy saw the same cards far too often.
    good = _step("good", interval=interval, ease_factor=ease, repetitions=repetitions)
    easy = _step("easy", interval=interval, ease_factor=ease, repetitions=repetitions)
    assert easy.interval > good.interval


def test_the_real_card_that_came_back_too_soon():
    # Card 289 on the dev account: good (+1 day), then easy gave +2 days.
    s = _step("good", repetitions=0)
    s = _step("easy", interval=s.interval, ease_factor=s.ease_factor, repetitions=s.repetitions)
    assert s.interval >= 4


@pytest.mark.parametrize("interval", [2, 4, 10])
def test_good_never_shortens_a_gap_easy_already_earned(interval):
    s = _step("good", interval=interval, ease_factor=2.5, repetitions=1)
    assert s.interval >= interval


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


# ---- daily budget ----------------------------------------------------------
# Two weeks away leaves 312 cards owed. Shown as one number, that is the moment
# a learner gives up — the "debt spiral". So a day has a share, and new cards
# wait while debt is owed: every card learned today is a review owed tomorrow.

def test_a_fresh_day_has_the_whole_allowance():
    b = sm2.daily_budget(review_limit=40, new_limit=10,
                         reviewed_today=0, introduced_today=0, due_now=12)
    assert b == sm2.DailyBudget(reviews_left=40, new_left=10)


def test_reviews_done_today_use_up_the_allowance():
    b = sm2.daily_budget(review_limit=40, new_limit=10,
                         reviewed_today=35, introduced_today=0, due_now=0)
    assert b.reviews_left == 5


def test_the_allowance_never_goes_negative():
    # Studying past the cap in browse mode is allowed; it just leaves nothing.
    b = sm2.daily_budget(review_limit=40, new_limit=10,
                         reviewed_today=55, introduced_today=14, due_now=0)
    assert b == sm2.DailyBudget(reviews_left=0, new_left=0)


def test_new_cards_wait_while_more_is_owed_than_today_can_clear():
    b = sm2.daily_budget(review_limit=40, new_limit=10,
                         reviewed_today=0, introduced_today=0, due_now=312)
    assert b.new_left == 0


def test_new_cards_return_once_today_can_clear_what_is_owed():
    b = sm2.daily_budget(review_limit=40, new_limit=10,
                         reviewed_today=0, introduced_today=0, due_now=40)
    assert b.new_left == 10


def test_new_cards_already_introduced_today_count():
    b = sm2.daily_budget(review_limit=40, new_limit=10,
                         reviewed_today=0, introduced_today=7, due_now=0)
    assert b.new_left == 3


def test_owing_what_is_left_of_today_still_pauses_new_cards():
    # 35 of 40 done, but 10 still due: today cannot clear them.
    b = sm2.daily_budget(review_limit=40, new_limit=10,
                         reviewed_today=35, introduced_today=0, due_now=10)
    assert b.new_left == 0


# ---- rank_due_cards with a budget --------------------------------------------

def test_the_queue_holds_only_todays_share_of_the_debt():
    cards = [_card(i) for i in range(1, 11)]
    schedule = {i: TODAY - timedelta(days=i) for i in range(1, 11)}
    out = sm2.rank_due_cards(cards, schedule, TODAY, limit=50,
                             budget=sm2.DailyBudget(reviews_left=3, new_left=10))
    # Most overdue first, and only three of them.
    assert [c["id"] for c in out] == [10, 9, 8]


def test_new_cards_are_capped_separately():
    cards = [_card(i) for i in range(1, 6)]
    out = sm2.rank_due_cards(cards, {}, TODAY, limit=50,
                             budget=sm2.DailyBudget(reviews_left=40, new_left=2))
    assert [c["id"] for c in out] == [1, 2]


def test_a_paused_new_allowance_shows_no_new_cards():
    cards = [_card(1), _card(2)]
    out = sm2.rank_due_cards(cards, {1: TODAY}, TODAY, limit=50,
                             budget=sm2.DailyBudget(reviews_left=40, new_left=0))
    assert [c["id"] for c in out] == [1]


def test_without_a_budget_ranking_is_unchanged():
    cards = [_card(i) for i in range(1, 6)]
    assert len(sm2.rank_due_cards(cards, {}, TODAY, limit=50)) == 5


# ---- todays_share ----------------------------------------------------------
# What the dashboard says: the share for today, and honestly, what waits.

def test_todays_share_is_what_the_budget_allows():
    counts = {"due": 312, "overdue": 300, "new": 20}
    share = sm2.todays_share(counts, sm2.DailyBudget(reviews_left=40, new_left=0))
    assert share == {"today": 40, "later": 272, "new_paused": True}


def test_a_small_debt_is_all_for_today():
    counts = {"due": 12, "overdue": 2, "new": 5}
    share = sm2.todays_share(counts, sm2.DailyBudget(reviews_left=40, new_left=10))
    assert share == {"today": 17, "later": 0, "new_paused": False}


def test_new_cards_held_by_the_daily_cap_are_not_called_paused():
    # The daily new allowance is spent; that is a normal day, not debt.
    counts = {"due": 0, "overdue": 0, "new": 20}
    share = sm2.todays_share(counts, sm2.DailyBudget(reviews_left=40, new_left=0))
    assert share == {"today": 0, "later": 0, "new_paused": False}


# ---- todays_activity -------------------------------------------------------
# Rows are {"flashcard_id", "day", "is_seed"}; `day` is the review's local date.

def _answer(card, day, seed=False):
    return {"flashcard_id": card, "day": day, "is_seed": seed}


def test_a_card_first_studied_today_was_introduced_today():
    reviewed, introduced = sm2.todays_activity([_answer(1, TODAY)], TODAY)
    assert (reviewed, introduced) == (0, 1)


def test_a_card_studied_before_counts_as_reviewed_today():
    rows = [_answer(1, TODAY - timedelta(days=3)), _answer(1, TODAY)]
    assert sm2.todays_activity(rows, TODAY) == (1, 0)


def test_a_card_studied_twice_today_counts_once():
    rows = [_answer(1, TODAY - timedelta(days=3)), _answer(1, TODAY), _answer(1, TODAY)]
    assert sm2.todays_activity(rows, TODAY) == (1, 0)


def test_a_seed_row_is_not_a_recall():
    # A seed carries a schedule to a regenerated card; nobody answered anything.
    assert sm2.todays_activity([_answer(1, TODAY, seed=True)], TODAY) == (0, 0)


def test_a_seeded_card_answered_today_is_a_review_not_a_new_card():
    # It inherited its place in the schedule, so it was never new.
    rows = [_answer(1, TODAY - timedelta(days=1), seed=True), _answer(1, TODAY)]
    assert sm2.todays_activity(rows, TODAY) == (1, 0)


def test_yesterdays_work_does_not_count_today():
    assert sm2.todays_activity([_answer(1, TODAY - timedelta(days=1))], TODAY) == (0, 0)


# ---- exam priority ---------------------------------------------------------
# A notebook with a test this week goes first. When a day cannot clear the
# debt, at least it clears the part that matters soonest.

def _nb_card(cid, notebook):
    return {"id": cid, "question": "Q?", "notebook_id": notebook}


def test_exam_days_counts_days_until_each_notebooks_test():
    tests = [{"notebook_id": 7, "day": TODAY + timedelta(days=3)}]
    assert sm2.exam_days(tests, TODAY) == {7: 3}


def test_a_test_today_is_zero_days_away():
    assert sm2.exam_days([{"notebook_id": 7, "day": TODAY}], TODAY) == {7: 0}


def test_the_soonest_of_a_notebooks_tests_wins():
    tests = [{"notebook_id": 7, "day": TODAY + timedelta(days=6)},
             {"notebook_id": 7, "day": TODAY + timedelta(days=2)}]
    assert sm2.exam_days(tests, TODAY) == {7: 2}


def test_a_test_beyond_the_window_gives_no_priority():
    tests = [{"notebook_id": 7, "day": TODAY + timedelta(days=8)}]
    assert sm2.exam_days(tests, TODAY) == {}


def test_a_test_already_sat_gives_no_priority():
    tests = [{"notebook_id": 7, "day": TODAY - timedelta(days=1)}]
    assert sm2.exam_days(tests, TODAY) == {}


def test_cards_for_a_test_this_week_come_before_older_debt():
    cards = [_nb_card(1, notebook=1), _nb_card(2, notebook=2)]
    schedule = {1: TODAY - timedelta(days=20), 2: TODAY - timedelta(days=1)}
    out = sm2.rank_due_cards(cards, schedule, TODAY, limit=5, exam_days={2: 3})
    assert [c["id"] for c in out] == [2, 1]


def test_the_sooner_test_goes_first():
    cards = [_nb_card(1, notebook=1), _nb_card(2, notebook=2)]
    schedule = {1: TODAY, 2: TODAY}
    out = sm2.rank_due_cards(cards, schedule, TODAY, limit=5, exam_days={1: 5, 2: 1})
    assert [c["id"] for c in out] == [2, 1]


def test_within_one_test_the_most_overdue_still_leads():
    cards = [_nb_card(1, notebook=9), _nb_card(2, notebook=9)]
    schedule = {1: TODAY - timedelta(days=1), 2: TODAY - timedelta(days=6)}
    out = sm2.rank_due_cards(cards, schedule, TODAY, limit=5, exam_days={9: 2})
    assert [c["id"] for c in out] == [2, 1]


def test_new_cards_for_a_test_this_week_come_first_among_new():
    cards = [_nb_card(1, notebook=1), _nb_card(2, notebook=2)]
    out = sm2.rank_due_cards(cards, {}, TODAY, limit=5, exam_days={2: 4})
    assert [c["id"] for c in out] == [2, 1]


def test_the_days_share_is_filled_with_the_test_first():
    cards = [_nb_card(i, notebook=1) for i in range(1, 4)] + [_nb_card(9, notebook=2)]
    schedule = {i: TODAY - timedelta(days=10) for i in (1, 2, 3)}
    schedule[9] = TODAY
    out = sm2.rank_due_cards(cards, schedule, TODAY, limit=50,
                             budget=sm2.DailyBudget(reviews_left=2, new_left=0),
                             exam_days={2: 1})
    assert [c["id"] for c in out] == [9, 1]


def test_each_card_says_how_far_its_test_is():
    # The study page can then explain why the order changed.
    cards = [_nb_card(1, notebook=1), _nb_card(2, notebook=2)]
    out = sm2.rank_due_cards(cards, {1: TODAY, 2: TODAY}, TODAY, limit=5, exam_days={2: 3})
    by_id = {c["id"]: c for c in out}
    assert by_id[2]["exam_in_days"] == 3
    assert by_id[1]["exam_in_days"] is None


def test_cards_without_a_notebook_are_ranked_as_before():
    out = sm2.rank_due_cards([_card(1), _card(2)], {1: TODAY, 2: TODAY}, TODAY,
                             limit=5, exam_days={5: 1})
    assert [c["id"] for c in out] == [1, 2]


# ---- new cards paced to the test -------------------------------------------
# A test this week overrides the debt pause for its own new cards, spread over
# the days left so every card has been seen once before the test. Several
# subjects on one day each get their own pace.

def test_new_cards_are_spread_over_the_days_left():
    assert sm2.exam_new_allowance({7: 15}, {}, {7: 3}) == {7: 5}


def test_three_subjects_on_one_day_each_get_their_share():
    # Three tests in three days, fifteen unseen cards each: 45 cards, 15 a day.
    unseen = {1: 15, 2: 15, 3: 15}
    allowance = sm2.exam_new_allowance(unseen, {}, {1: 3, 2: 3, 3: 3})
    assert allowance == {1: 5, 2: 5, 3: 5}


def test_a_test_tomorrow_means_everything_today():
    assert sm2.exam_new_allowance({7: 15}, {}, {7: 1}) == {7: 15}


def test_a_test_today_means_everything_now():
    assert sm2.exam_new_allowance({7: 15}, {}, {7: 0}) == {7: 15}


def test_an_uneven_split_rounds_up_so_nothing_is_left_for_the_test():
    assert sm2.exam_new_allowance({7: 16}, {}, {7: 3}) == {7: 6}


def test_the_pace_holds_through_the_day():
    # 15 unseen this morning, 5 learned since: today's share is done. Pacing
    # from what is left now would hand out more every time the page reloads.
    assert sm2.exam_new_allowance({7: 10}, {7: 5}, {7: 3}) == {7: 0}


def test_a_notebook_with_nothing_unseen_needs_no_allowance():
    assert sm2.exam_new_allowance({}, {}, {7: 3}) == {7: 0}


def test_in_debt_the_tests_new_cards_still_come():
    cards = [_nb_card(1, notebook=1), _nb_card(2, notebook=2), _nb_card(3, notebook=2)]
    out = sm2.rank_due_cards(cards, {}, TODAY, limit=50,
                             budget=sm2.DailyBudget(reviews_left=40, new_left=0),
                             exam_days={2: 3}, exam_new={2: 2})
    assert [c["id"] for c in out] == [2, 3]


def test_the_tests_allowance_is_on_top_of_the_normal_new_cards():
    cards = [_nb_card(1, notebook=1), _nb_card(2, notebook=2), _nb_card(3, notebook=2)]
    out = sm2.rank_due_cards(cards, {}, TODAY, limit=50,
                             budget=sm2.DailyBudget(reviews_left=40, new_left=1),
                             exam_days={2: 3}, exam_new={2: 1})
    # One for the test's pace, then the day's one ordinary new card.
    assert [c["id"] for c in out] == [2, 3]


def test_todays_share_counts_the_tests_new_cards():
    # 15 of the 20 new cards belong to a test; all 15 are due to be seen today.
    counts = {"due": 312, "overdue": 300, "new": 20}
    share = sm2.todays_share(counts, sm2.DailyBudget(reviews_left=40, new_left=0),
                             exam_new_today=15, exam_unseen=15)
    assert share == {"today": 55, "later": 272, "new_paused": True}


def test_a_tests_cards_saved_for_later_days_are_paced_not_paused():
    # Every new card belongs to a test; 5 today, 10 on the days before it.
    counts = {"due": 312, "overdue": 300, "new": 15}
    share = sm2.todays_share(counts, sm2.DailyBudget(reviews_left=40, new_left=0),
                             exam_new_today=5, exam_unseen=15)
    assert share["new_paused"] is False
    assert share["today"] == 45
