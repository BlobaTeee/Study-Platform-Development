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


def test_parse_handles_missing_or_malformed_tags():
    assert ins.parse_source_ids(None) == []
    assert ins.parse_source_ids("") == []
    assert ins.parse_source_ids("source:") == []
    assert ins.parse_source_ids("not-a-source-tag") == []
    assert ins.parse_source_ids("source:1,abc,3") == [1, 3]  # skip junk, keep valid


# ---- per_source_accuracy ---------------------------------------------------

def test_accuracy_per_document_weakest_first():
    cards = [_card(1, correct=1, incorrect=9, tags="source:1"),   # 10% -> weakest
             _card(2, correct=9, incorrect=1, tags="source:2")]   # 90%
    out = ins.per_source_accuracy(cards, {1: "Weak Doc", 2: "Strong Doc"})
    assert [s["title"] for s in out] == ["Weak Doc", "Strong Doc"]
    assert out[0]["accuracy"] == pytest.approx(10.0)
    assert out[1]["accuracy"] == pytest.approx(90.0)


def test_multi_source_card_counts_toward_each_document():
    cards = [_card(1, correct=1, incorrect=1, tags="source:1,2")]
    out = ins.per_source_accuracy(cards, {1: "A", 2: "B"})
    assert {s["title"] for s in out} == {"A", "B"}
    assert all(s["cards"] == 1 for s in out)


def test_unreviewed_document_reports_none_not_zero():
    # 0% would wrongly imply the user failed it; they simply haven't studied it.
    cards = [_card(1, correct=0, incorrect=0, tags="source:1")]
    out = ins.per_source_accuracy(cards, {1: "Fresh Doc"})
    assert out[0]["accuracy"] is None
    assert out[0]["reviews"] == 0


def test_ignores_cards_whose_source_no_longer_exists():
    cards = [_card(1, correct=1, incorrect=0, tags="source:99")]
    assert ins.per_source_accuracy(cards, {1: "Only Doc"}) == []


def test_per_source_counts_cards_and_reviews():
    cards = [_card(1, correct=2, incorrect=1, tags="source:1"),
             _card(2, correct=1, incorrect=0, tags="source:1")]
    out = ins.per_source_accuracy(cards, {1: "Doc"})
    assert out[0]["cards"] == 2
    assert out[0]["reviews"] == 4


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
