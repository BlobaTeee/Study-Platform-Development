"""Shape a raw model quiz question into a valid, answerable multiple-choice item.

Small local models often emit quiz JSON where the correct answer is not among
the options, or give too few/placeholder options. This normalizer builds the
options in code from a correct answer + distractors, which *structurally*
guarantees the correct answer is one of the choices. Accepts both the
distractor schema and the legacy ``options`` schema (e.g. Gemini) for
back-compatibility. No Django imports so it can be unit-tested in isolation.
"""
from __future__ import annotations

import re

from .units import unit_symbols

MAX_OPTIONS = 4  # correct answer + up to 3 distractors

# "C) …", "(c) …", "B. …", "D: …" — a single letter A–D (the only letters a
# four-option paper uses) followed by a separator. "C++ templates", "B cells"
# and "D-day" do not match: no separator, or the letter is part of a word.
_OPTION_PREFIX = re.compile(r"^\(?[A-Da-d][\).:]\s+")


def strip_option_prefix(text: str) -> str:
    """The option without the letter a model sometimes numbers it with."""
    return _OPTION_PREFIX.sub("", text.strip()).strip()


def shape_quiz_question(raw: dict, rng) -> dict | None:
    """Return a normalized MCQ dict, or None if it can't be made answerable.

    Output: {question_text, question_type, options, correct_answer, explanation}
    with ``correct_answer in options`` and 2..MAX_OPTIONS options.
    """
    question = (raw.get("question_text") or raw.get("question") or "").strip()
    # Units become symbols in the options and the answer alike, so the
    # option the student picks still equals the stored answer.
    correct = unit_symbols(strip_option_prefix(raw.get("correct_answer") or raw.get("answer") or ""))
    if not question or not correct:
        return None
    if str(raw.get("kind") or "").strip().lower() == "fill_blank":
        # One blank, a short term, not shown elsewhere in the sentence: a
        # blank with no single answer would be marked on luck. Imported here
        # so the choice shaping above stays loadable without the backend.
        from flashcards.services.card_format import checked_cloze
        sentence = checked_cloze(question, correct)
        if sentence is None:
            return None
        return {"question_text": sentence, "question_type": "fill_blank", "options": [],
                "correct_answer": correct, "explanation": (raw.get("explanation") or "").strip() or None}

    # Prefer explicit distractors; else derive them from a legacy options list.
    candidates = raw.get("distractors")
    if not candidates:
        candidates = raw.get("options") or []
    distractors = [unit_symbols(strip_option_prefix(str(d))) for d in candidates if str(d).strip()]
    distractors = [d for d in distractors if d]

    # Drop anything equal to the correct answer or duplicated (case-insensitive).
    seen = {correct.lower()}
    unique = []
    for d in distractors:
        if d.lower() not in seen:
            seen.add(d.lower())
            unique.append(d)

    if not unique:
        return None  # no distinct wrong answer -> can't form a choice

    options = [correct] + unique[: MAX_OPTIONS - 1]
    rng.shuffle(options)

    explanation = (raw.get("explanation") or "").strip()
    return {
        "question_text": question,
        "question_type": "multiple_choice",
        "options": options,
        "correct_answer": correct,
        "explanation": explanation or None,
    }
