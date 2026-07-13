"""Thin-source guard: give users an actionable message instead of empty output."""
import pytest

from ml_pipeline.source_guard import (
    InsufficientSourceTextError,
    check_source_text,
)


def _text(n_words: int) -> str:
    return " ".join(["word"] * n_words)


def test_passes_when_text_meets_minimum():
    # Exactly at the floor is acceptable (no exception).
    check_source_text(_text(40), kind="quiz", min_words=40)


def test_raises_below_minimum():
    with pytest.raises(InsufficientSourceTextError):
        check_source_text(_text(10), kind="quiz", min_words=40)


def test_error_is_a_valueerror_so_the_api_returns_400():
    # The DRF view catches ValueError -> 400 {detail: message}.
    assert issubclass(InsufficientSourceTextError, ValueError)


def test_message_is_actionable_and_mentions_the_kind():
    with pytest.raises(InsufficientSourceTextError) as exc:
        check_source_text(_text(5), kind="flashcard set", min_words=15)
    msg = str(exc.value).lower()
    assert "flashcard set" in msg
    assert "5" in msg          # actual word count
    assert "15" in msg         # required minimum
    assert "add more text" in msg or "longer" in msg


def test_empty_or_whitespace_text_raises():
    with pytest.raises(InsufficientSourceTextError):
        check_source_text("   \n\t ", kind="quiz", min_words=40)
    with pytest.raises(InsufficientSourceTextError):
        check_source_text("", kind="quiz", min_words=40)


def test_word_count_ignores_punctuation_and_symbols():
    # 3 real words, plenty of punctuation -> still below a floor of 10.
    with pytest.raises(InsufficientSourceTextError) as exc:
        check_source_text("one, two --- three!!! ... @#$%", kind="quiz", min_words=10)
    assert "3" in str(exc.value)
