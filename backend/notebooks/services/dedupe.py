"""Deciding which generated flashcards are actually new to a document.

Generating appends rather than replaces, so a document generated from twice
would otherwise carry the same fact on two cards with two independent schedules
— and the learner would review one thing on two different days, which is the
waste spaced repetition exists to remove.

No Django imports: the caller passes the questions already on file as plain
strings, so this stays unit-testable in isolation.
"""
from __future__ import annotations

import re

_WHITESPACE = re.compile(r"\s+")
_OUTER_NOISE = re.compile(r"^[\W_]+|[\W_]+$")


def normalize_question(text: str | None) -> str:
    """Fold a question to a key two phrasings of the same prompt will share.

    The model varies case and its closing '?' between runs while asking the same
    thing, so neither can be allowed to make a question look new.
    """
    if not text:
        return ""
    folded = _WHITESPACE.sub(" ", text).strip().casefold()
    return _OUTER_NOISE.sub("", folded)


def new_flashcards(items: list[dict], existing_questions: list[str]) -> list[dict]:
    """The generated items worth saving, in the order they arrived.

    Drops anything the document already asks and anything the batch repeats to
    itself — excerpts overlap, so one run can raise the same fact twice. Items
    are returned as given, since the caller still needs their answers.

    An empty result means the document had nothing further to add. That is a
    finished document, not a failed generation.
    """
    seen = {normalize_question(q) for q in existing_questions}
    seen.discard("")

    fresh = []
    for item in items:
        key = normalize_question(item.get("question"))
        if not key or key in seen:
            continue
        seen.add(key)
        fresh.append(item)
    return fresh
