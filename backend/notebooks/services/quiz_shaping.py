"""Shape a raw model quiz question into a valid, answerable multiple-choice item.

Small local models often emit quiz JSON where the correct answer is not among
the options, or give too few/placeholder options. This normalizer builds the
options in code from a correct answer + distractors, which *structurally*
guarantees the correct answer is one of the choices. Accepts both the
distractor schema and the legacy ``options`` schema (e.g. Gemini) for
back-compatibility. No Django imports so it can be unit-tested in isolation.
"""
from __future__ import annotations

MAX_OPTIONS = 4  # correct answer + up to 3 distractors


def shape_quiz_question(raw: dict, rng) -> dict | None:
    """Return a normalized MCQ dict, or None if it can't be made answerable.

    Output: {question_text, question_type, options, correct_answer, explanation}
    with ``correct_answer in options`` and 2..MAX_OPTIONS options.
    """
    question = (raw.get("question_text") or raw.get("question") or "").strip()
    correct = (raw.get("correct_answer") or raw.get("answer") or "").strip()
    if not question or not correct:
        return None

    # Prefer explicit distractors; else derive them from a legacy options list.
    candidates = raw.get("distractors")
    if not candidates:
        candidates = raw.get("options") or []
    distractors = [str(d).strip() for d in candidates if str(d).strip()]

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
