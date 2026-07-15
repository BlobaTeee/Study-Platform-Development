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


def _card(cid, correct=0, incorrect=0, tags="source:1", question="Q?"):
    return {"id": cid, "question": question, "correct_count": correct,
            "incorrect_count": incorrect, "tags": tags}


# ---- card_priority ---------------------------------------------------------

def test_never_reviewed_card_sits_mid_priority():
    # Unknown mastery -> 0.5, worth testing but not above known-weak cards.
    assert ins.card_priority(0, 0) == pytest.approx(0.5)


def test_always_wrong_is_higher_priority_than_never_reviewed():
    assert ins.card_priority(0, 4) > ins.card_priority(0, 0)


def test_always_correct_is_lower_priority_than_never_reviewed():
    assert ins.card_priority(4, 0) < ins.card_priority(0, 0)


def test_priority_stays_within_zero_and_one():
    for c, i in [(0, 0), (99, 0), (0, 99), (5, 5)]:
        assert 0.0 < ins.card_priority(c, i) < 1.0


# ---- rank_weak_cards -------------------------------------------------------

def test_ranks_weakest_first_and_respects_limit():
    cards = [_card(1, correct=9, incorrect=0),   # strong -> low priority
             _card(2, correct=0, incorrect=9),   # weak   -> high priority
             _card(3, correct=0, incorrect=0)]   # unknown-> mid
    out = ins.rank_weak_cards(cards, limit=2)
    assert [c["id"] for c in out] == [2, 3]
    assert out[0]["priority"] > out[1]["priority"]


def test_rank_includes_review_counts_for_display():
    out = ins.rank_weak_cards([_card(1, correct=2, incorrect=3)], limit=5)
    assert out[0]["correct_count"] == 2
    assert out[0]["incorrect_count"] == 3
    assert out[0]["question"] == "Q?"


def test_rank_empty_returns_empty():
    assert ins.rank_weak_cards([], limit=5) == []


def test_rank_is_deterministic_on_ties():
    cards = [_card(2), _card(1)]  # identical priority -> stable by id
    assert [c["id"] for c in ins.rank_weak_cards(cards, limit=5)] == [1, 2]


# ---- parse_source_ids ------------------------------------------------------

def test_parses_single_and_multi_source_tags():
    assert ins.parse_source_ids("source:5") == [5]
    assert ins.parse_source_ids("source:1,2") == [1, 2]


def test_parses_the_tag_quizzes_bury_in_their_description():
    # Flashcards store a bare tag; quizzes embed one in prose. Reading only the
    # bare form is what silently kept every quiz out of per-document mastery.
    assert ins.parse_source_ids("Generated from Week 2 Lecture [source:13]") == [13]
    assert ins.parse_source_ids("Test your knowledge. [source:1,2]") == [1, 2]


def test_parse_handles_missing_or_malformed_tags():
    assert ins.parse_source_ids(None) == []
    assert ins.parse_source_ids("") == []
    assert ins.parse_source_ids("source:") == []
    assert ins.parse_source_ids("not-a-source-tag") == []
    assert ins.parse_source_ids("source:1,abc,3") == [1, 3]  # skip junk, keep valid


# ---- study events ----------------------------------------------------------
# "How well do I know this document?" must not depend on which study mode
# produced the evidence, so each mode is adapted to a common event shape and a
# new mode later only needs its own adapter.

def test_flashcard_events_carry_the_cards_review_tally():
    events = ins.flashcard_events([
        {"id": 1, "tags": "source:3", "correct_count": 2, "incorrect_count": 1}
    ])
    assert events == [
        {"kind": ins.KIND_FLASHCARD, "source_ids": [3], "correct": 2, "incorrect": 1}
    ]


def test_quiz_events_count_each_questions_answers():
    questions = [{"id": 9, "quiz_description": "Quiz [source:3]"}]
    answers = [{"question_id": 9, "is_correct": True},
               {"question_id": 9, "is_correct": False}]
    assert ins.quiz_events(questions, answers) == [
        {"kind": ins.KIND_QUIZ, "source_ids": [3], "correct": 1, "incorrect": 1}
    ]


def test_unanswered_quiz_question_is_still_an_item():
    # Mirrors an unreviewed flashcard: something left to study, no evidence yet.
    events = ins.quiz_events([{"id": 9, "quiz_description": "Quiz [source:3]"}], [])
    assert events[0]["correct"] == 0
    assert events[0]["incorrect"] == 0


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
    cards = [{"id": 1, "question": "Q?", "tags": "source:1"}]
    out = ins.attach_review_counts(cards, {1: {"correct": 3, "incorrect": 1}})
    assert out[0]["correct_count"] == 3
    assert out[0]["incorrect_count"] == 1


def test_attach_defaults_an_unreviewed_card_to_zero():
    out = ins.attach_review_counts([{"id": 7, "question": "Q?", "tags": "source:1"}], {})
    assert out[0]["correct_count"] == 0
    assert out[0]["incorrect_count"] == 0


def test_attach_keeps_the_original_card_fields():
    out = ins.attach_review_counts([{"id": 1, "question": "Q?", "tags": "source:2"}], {})
    assert out[0]["question"] == "Q?"
    assert out[0]["tags"] == "source:2"


def test_attached_counts_feed_the_existing_ranking():
    # The two halves must compose: reviews -> counts -> weakest-first ranking.
    cards = [{"id": 1, "question": "strong", "tags": "source:1"},
             {"id": 2, "question": "weak", "tags": "source:1"}]
    reviews = [_review(1, "good"), _review(1, "good"),
               _review(2, "again"), _review(2, "again")]
    scored = ins.attach_review_counts(cards, ins.tally_reviews(reviews))
    assert [c["id"] for c in ins.rank_weak_cards(scored, limit=2)] == [2, 1]
