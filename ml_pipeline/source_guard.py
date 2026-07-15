"""Pre-flight check that a source has enough text to generate study content.

Kept dependency-free (no spaCy/sklearn) so it can run as a fast guard at the
API boundary and give users an actionable message instead of empty output.
"""
from __future__ import annotations

import re

# Heuristic floors. A multiple-choice quiz needs several distinct candidate
# terms to form distractors, so it needs more text than a flashcard set.
MIN_WORDS_QUIZ = 40
MIN_WORDS_FLASHCARDS = 15

_WORD = re.compile(r"\w+")


class InsufficientSourceTextError(ValueError):
    """Raised when a source is too thin to generate the requested content.

    Subclasses ValueError so the DRF view returns it as a 400 with the message.
    """


def word_count(text: str) -> int:
    return len(_WORD.findall(text or ""))


def check_source_text(text: str, *, kind: str, min_words: int) -> None:
    """Raise InsufficientSourceTextError if `text` has fewer than `min_words`."""
    count = word_count(text)
    if count < min_words:
        raise InsufficientSourceTextError(
            f"This source is too short to generate a {kind} "
            f"({count} words; needs at least {min_words}). "
            "Add more text or choose a longer document."
        )
