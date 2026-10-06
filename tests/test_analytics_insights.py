"""Analytics insights derived from the user's own cards (no fixed taxonomy)."""
import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "analytics" / "insights.py")


def _load():
    spec = importlib.util.spec_from_file_location("analytics_insights_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ins = _load()


# What to study next is answered by the SM-2 schedule (study_sessions.
# scheduling.rank_due_cards), not by ranking cards on how often they were
# failed: that ignored the schedule and could call up a card the algorithm had
# deliberately set aside for weeks.


# ---- study events ----------------------------------------------------------
# "How well do I know this document?" must not depend on which study mode
# produced the evidence, so each mode is adapted to a common event shape and a
# new mode later only needs its own adapter. Source ids arrive already
# resolved from the relation; the adapters do no parsing.

def test_flashcard_events_carry_the_cards_review_tally():
    events = ins.flashcard_events([
        {"id": 1, "source_ids": [3], "correct_count": 2, "incorrect_count": 1}
    ])
    assert events == [
        {"kind": ins.KIND_FLASHCARD, "source_ids": [3], "correct": 2, "incorrect": 1}
    ]


def test_quiz_events_count_each_questions_answers():
    questions = [{"id": 9, "source_ids": [3]}]
    answers = [{"question_id": 9, "is_correct": True},
               {"question_id": 9, "is_correct": False}]
    assert ins.quiz_events(questions, answers) == [
        {"kind": ins.KIND_QUIZ, "source_ids": [3], "correct": 1, "incorrect": 1}
    ]


def test_unanswered_quiz_question_is_still_an_item():
    # Mirrors an unreviewed flashcard: something left to study, no evidence yet.
    events = ins.quiz_events([{"id": 9, "source_ids": [3]}], [])
    assert events[0]["correct"] == 0
    assert events[0]["incorrect"] == 0


def test_an_item_with_no_sources_is_still_an_event():
    # A hand-written card, or one whose only source was deleted: it is studied
    # like any other, it just counts toward no document.
    events = ins.flashcard_events([{"id": 1, "correct_count": 1, "incorrect_count": 0}])
    assert events == [
        {"kind": ins.KIND_FLASHCARD, "source_ids": [], "correct": 1, "incorrect": 0}
    ]


# ---- per_source_mastery ----------------------------------------------------

def _fc(source_ids, correct=0, incorrect=0):
    return {"kind": ins.KIND_FLASHCARD, "source_ids": source_ids,
            "correct": correct, "incorrect": incorrect}


def _qz(source_ids, correct=0, incorrect=0):
    return {"kind": ins.KIND_QUIZ, "source_ids": source_ids,
            "correct": correct, "incorrect": incorrect}


def test_quiz_evidence_counts_toward_the_document():
    # The defect this replaces: mastery ignored every quiz answer on record.
    out = ins.per_source_mastery([_qz([1], correct=3, incorrect=1)], {1: "Doc"})
    assert out[0]["accuracy"] == pytest.approx(75.0)
    assert out[0]["questions"] == 1
    assert out[0]["reviews"] == 4


def test_both_study_modes_pool_into_one_accuracy():
    events = [_fc([1], correct=1, incorrect=1), _qz([1], correct=3, incorrect=1)]
    out = ins.per_source_mastery(events, {1: "Doc"})
    assert out[0]["cards"] == 1
    assert out[0]["questions"] == 1
    assert out[0]["reviews"] == 6
    assert out[0]["accuracy"] == pytest.approx(4 / 6 * 100, abs=0.1)


def test_mastery_puts_the_weakest_document_first():
    events = [_fc([1], correct=1, incorrect=9), _qz([2], correct=9, incorrect=1)]
    out = ins.per_source_mastery(events, {1: "Weak Doc", 2: "Strong Doc"})
    assert [s["title"] for s in out] == ["Weak Doc", "Strong Doc"]
    assert out[0]["accuracy"] == pytest.approx(10.0)


def test_item_spanning_two_documents_counts_for_each():
    out = ins.per_source_mastery([_fc([1, 2], correct=1, incorrect=1)], {1: "A", 2: "B"})
    assert {s["title"] for s in out} == {"A", "B"}
    assert all(s["cards"] == 1 for s in out)


def test_unstudied_document_reports_none_not_zero():
    # 0% would wrongly imply the user failed it; they simply haven't studied it.
    out = ins.per_source_mastery([_fc([1])], {1: "Fresh Doc"})
    assert out[0]["accuracy"] is None
    assert out[0]["reviews"] == 0


def test_mastery_ignores_items_whose_document_is_gone():
    assert ins.per_source_mastery([_fc([99], correct=1)], {1: "Only Doc"}) == []


def test_unstudied_documents_sort_last():
    events = [_fc([1]), _fc([2], correct=0, incorrect=5)]
    out = ins.per_source_mastery(events, {1: "Fresh", 2: "Failing"})
    assert [s["title"] for s in out] == ["Failing", "Fresh"]


def test_mastery_counts_items_and_answers_per_document():
    events = [_fc([1], correct=2, incorrect=1), _fc([1], correct=1),
              _qz([1], correct=0, incorrect=2)]
    out = ins.per_source_mastery(events, {1: "Doc"})
    assert out[0]["cards"] == 2
    assert out[0]["questions"] == 1
    assert out[0]["reviews"] == 6


# ---- tally_reviews ---------------------------------------------------------
# Counts come from the user's CardReview rows. Flashcard.correct_count and
# .incorrect_count exist on the model but nothing has ever written to them.

def _review(card_id, result):
    return {"flashcard_id": card_id, "result": result}


def test_good_and_easy_count_as_recalled():
    assert ins.tally_reviews([_review(1, "good"), _review(1, "easy")]) == {
        1: {"correct": 2, "incorrect": 0}
    }


def test_again_and_hard_count_as_forgotten():
    assert ins.tally_reviews([_review(1, "again"), _review(1, "hard")]) == {
        1: {"correct": 0, "incorrect": 2}
    }


def test_tally_keeps_cards_separate():
    tallies = ins.tally_reviews([_review(1, "good"), _review(2, "again")])
    assert tallies[1]["correct"] == 1
    assert tallies[2]["incorrect"] == 1


def test_tally_ignores_grades_it_does_not_recognise():
    assert ins.tally_reviews([_review(1, "good"), _review(1, "bogus")]) == {
        1: {"correct": 1, "incorrect": 0}
    }


def test_tally_of_no_reviews_is_empty():
    assert ins.tally_reviews([]) == {}


# ---- attach_review_counts --------------------------------------------------

def test_attach_fills_counts_from_the_review_record():
    cards = [{"id": 1, "question": "Q?", "source_ids": [1]}]
    out = ins.attach_review_counts(cards, {1: {"correct": 3, "incorrect": 1}})
    assert out[0]["correct_count"] == 3
    assert out[0]["incorrect_count"] == 1


def test_attach_defaults_an_unreviewed_card_to_zero():
    out = ins.attach_review_counts([{"id": 7, "question": "Q?", "source_ids": [1]}], {})
    assert out[0]["correct_count"] == 0
    assert out[0]["incorrect_count"] == 0


def test_attach_keeps_the_original_card_fields():
    out = ins.attach_review_counts([{"id": 1, "question": "Q?", "source_ids": [2]}], {})
    assert out[0]["question"] == "Q?"
    assert out[0]["source_ids"] == [2]


def test_attached_counts_reach_per_document_mastery():
    # The chain must compose: reviews -> counts -> events -> document accuracy.
    cards = [{"id": 1, "question": "recalled", "source_ids": [1]},
             {"id": 2, "question": "forgotten", "source_ids": [1]}]
    reviews = [_review(1, "good"), _review(1, "good"),
               _review(2, "again"), _review(2, "again")]
    scored = ins.attach_review_counts(cards, ins.tally_reviews(reviews))
    out = ins.per_source_mastery(ins.flashcard_events(scored), {1: "Doc"})
    assert out[0]["accuracy"] == pytest.approx(50.0)
    assert out[0]["cards"] == 2


# ---- per_notebook_mastery --------------------------------------------------

# source id -> notebook id. Sources 1 and 2 share notebook 10; source 3 is in 20.
NB_OF = {1: 10, 2: 10, 3: 20}
NB_TITLES = {10: "Biology", 20: "History"}


def test_notebook_mastery_pools_its_sources():
    events = [_fc([1], correct=1, incorrect=1), _qz([2], correct=3, incorrect=1)]
    out = ins.per_notebook_mastery(events, NB_OF, NB_TITLES)
    assert [n["notebook_id"] for n in out] == [10]
    assert out[0]["title"] == "Biology"
    assert out[0]["cards"] == 1
    assert out[0]["questions"] == 1
    assert out[0]["reviews"] == 6
    assert out[0]["accuracy"] == pytest.approx(4 / 6 * 100, abs=0.1)


def test_item_spanning_two_sources_in_one_notebook_counts_once():
    # Summing per-source rows would count this card twice for Biology.
    out = ins.per_notebook_mastery([_fc([1, 2], correct=1, incorrect=1)], NB_OF, NB_TITLES)
    assert len(out) == 1
    assert out[0]["cards"] == 1
    assert out[0]["reviews"] == 2


def test_notebook_mastery_puts_the_weakest_first():
    events = [_fc([3], correct=1, incorrect=9), _qz([1], correct=9, incorrect=1)]
    out = ins.per_notebook_mastery(events, NB_OF, NB_TITLES)
    assert [n["title"] for n in out] == ["History", "Biology"]


def test_notebook_with_nothing_studied_is_absent():
    out = ins.per_notebook_mastery([_fc([1])], NB_OF, NB_TITLES)
    assert [n["title"] for n in out] == ["Biology"]
    assert out[0]["accuracy"] is None


def test_event_pointing_at_an_orphan_source_is_ignored():
    # A source deleted from its notebook, or one that never existed.
    out = ins.per_notebook_mastery([_fc([99], correct=1)], NB_OF, NB_TITLES)
    assert out == []


# ---- daily_activity ----------------------------------------------------------
# The Analytics page shows the last fourteen days as one strip. Every day is
# present, studied or not — a gap is information — oldest first.

from datetime import date as _date


def _rev(day, result="good"):
    return {"date": _date(2026, 9, day), "result": result}


def test_activity_covers_every_day_of_the_window_oldest_first():
    out = ins.daily_activity([], [], today=_date(2026, 9, 16), days=14)
    assert [d["date"] for d in out["days"]] == [
        _date(2026, 9, 3) + __import__("datetime").timedelta(days=i) for i in range(14)]
    assert out["days"][-1]["date"] == _date(2026, 9, 16)


def test_a_day_with_no_study_is_present_with_zeros_and_no_accuracy():
    out = ins.daily_activity([], [], today=_date(2026, 9, 16), days=3)
    assert out["days"][0] == {"date": _date(2026, 9, 14), "reviews": 0, "correct": 0,
                              "accuracy": None, "mock_scores": []}


def test_reviews_are_counted_and_graded_per_day():
    reviews = [_rev(15, "good"), _rev(15, "hard"), _rev(15, "easy"), _rev(16, "again")]
    out = ins.daily_activity(reviews, [], today=_date(2026, 9, 16), days=3)
    d15, d16 = out["days"][1], out["days"][2]
    assert (d15["reviews"], d15["correct"], d15["accuracy"]) == (3, 2, 66.7)
    assert (d16["reviews"], d16["correct"], d16["accuracy"]) == (1, 0, 0.0)


def test_mock_test_scores_land_on_their_day():
    tests = [{"date": _date(2026, 9, 15), "score": 40.0},
             {"date": _date(2026, 9, 15), "score": 65.0}]
    out = ins.daily_activity([], tests, today=_date(2026, 9, 16), days=3)
    assert out["days"][1]["mock_scores"] == [40.0, 65.0]
    assert out["days"][2]["mock_scores"] == []


def test_activity_outside_the_window_is_ignored():
    out = ins.daily_activity([_rev(1)], [{"date": _date(2026, 9, 1), "score": 90.0}],
                             today=_date(2026, 9, 16), days=14)
    assert sum(d["reviews"] for d in out["days"]) == 0
    assert all(d["mock_scores"] == [] for d in out["days"])


def test_summary_totals_the_window():
    reviews = [_rev(10, "good"), _rev(12, "hard"), _rev(16, "good"), _rev(16, "good")]
    tests = [{"date": _date(2026, 9, 12), "score": 50.0}]
    out = ins.daily_activity(reviews, tests, today=_date(2026, 9, 16), days=14)
    assert out["summary"] == {"reviews": 4, "correct": 3, "accuracy": 75.0, "mock_tests": 1}


def test_summary_accuracy_is_none_when_nothing_was_reviewed():
    out = ins.daily_activity([], [], today=_date(2026, 9, 16), days=14)
    assert out["summary"] == {"reviews": 0, "correct": 0, "accuracy": None, "mock_tests": 0}


def test_unknown_grades_are_not_counted():
    # A seed row or a retired grade must not move the numbers.
    out = ins.daily_activity([_rev(16, "seed"), _rev(16, "good")], [],
                             today=_date(2026, 9, 16), days=1)
    assert (out["days"][0]["reviews"], out["days"][0]["correct"]) == (1, 1)
