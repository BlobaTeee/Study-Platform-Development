"""Keeping a document from teaching the same fact twice.

Generating flashcards appends rather than replaces, so pressing Generate again
on a document adds a fresh batch beside the old one. Without this, the same fact
lands on two cards carrying two independent schedules, and the learner reviews
it twice on two different days — the exact waste spaced repetition exists to
remove.
"""
import importlib.util
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "notebooks" / "services" / "dedupe.py")


def _load():
    spec = importlib.util.spec_from_file_location("dedupe_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dd = _load()


def _item(question, answer="A"):
    return {"question": question, "answer": answer}


# ---- normalize_question ----------------------------------------------------

def test_normalisation_ignores_case_and_padding():
    assert dd.normalize_question("  What Is A Model?  ") == dd.normalize_question("what is a model")


def test_normalisation_ignores_trailing_punctuation():
    # The model ends a question with '?' inconsistently between runs.
    assert dd.normalize_question("What is a model?") == dd.normalize_question("What is a model")


def test_normalisation_collapses_inner_whitespace():
    assert dd.normalize_question("What  is\na model?") == dd.normalize_question("What is a model?")


def test_normalisation_keeps_different_questions_apart():
    assert dd.normalize_question("What is a model?") != dd.normalize_question("What is a schema?")


def test_normalisation_of_nothing_is_empty():
    assert dd.normalize_question(None) == ""
    assert dd.normalize_question("   ") == ""
    assert dd.normalize_question("???") == ""


# ---- new_flashcards --------------------------------------------------------

def test_drops_an_item_the_document_already_has():
    out = dd.new_flashcards([_item("What is a conceptual model?")],
                            ["What is a conceptual model?"])
    assert out == []


def test_drops_a_near_match_that_differs_only_in_case_or_punctuation():
    # This is the shape the duplicates actually took across two runs.
    out = dd.new_flashcards([_item("what is a conceptual model")],
                            ["What is a conceptual model?"])
    assert out == []


def test_keeps_an_item_the_document_does_not_have():
    out = dd.new_flashcards([_item("What is a schema?")], ["What is a model?"])
    assert [i["question"] for i in out] == ["What is a schema?"]


def test_drops_a_repeat_inside_one_batch():
    # Excerpts overlap, so one run can raise the same fact twice by itself.
    out = dd.new_flashcards([_item("What is a model?"), _item("What is a model?")], [])
    assert len(out) == 1


def test_drops_an_item_with_no_question():
    assert dd.new_flashcards([_item(""), _item("   ")], []) == []


def test_keeps_the_original_item_untouched():
    # The caller still needs answer and difficulty off the item it passed in.
    item = {"question": "Q?", "answer": "A", "difficulty": "hard"}
    assert dd.new_flashcards([item], []) == [item]


def test_keeps_order_so_the_best_excerpt_still_leads():
    items = [_item("first"), _item("second"), _item("third")]
    assert [i["question"] for i in dd.new_flashcards(items, [])] == ["first", "second", "third"]


def test_everything_new_when_the_document_is_empty():
    items = [_item("a"), _item("b")]
    assert dd.new_flashcards(items, []) == items


def test_everything_dropped_when_the_document_is_exhausted():
    # Not a failure: the document simply had nothing further to give.
    assert dd.new_flashcards([_item("a"), _item("b")], ["a", "b"]) == []
