"""Regenerate a failed flashcard as a different question on the same concept.

A learner who keeps failing a card ends up memorising its wording rather than
the material, so re-study stops testing anything. This produces a fresh question
about the same concept, grounded in the source excerpt so the model cannot drift
onto material the learner never read.

No Django imports: the caller passes the card's text and its provider, so the
prompt building, parsing and fallback stay unit-testable in isolation.
"""
from __future__ import annotations

import re

from flashcards.services.card_format import ANSWER_RULES
from notebooks.services.writing_style import WRITING_STYLE, tidy_prose, tidy_question

BLANK = "______"
_WORD = re.compile(r"\w+")

# Below this many characters, a card carries too little to reformat into a
# meaningful question, so failing outright beats emitting nonsense.
MIN_REFORMAT_CHARS = 12


def _normalize(text: str | None) -> str:
    """Fold a question the way dedupe does, so 'the same' means the same here."""
    from notebooks.services.dedupe import normalize_question
    return normalize_question(text)


def build_variant_prompt(question: str, answer: str, excerpt: str) -> str:
    """Ask for one new question on the concept the failed card tests."""
    grounding = (
        f"\nGround the question in this source excerpt, and make it answerable "
        f"from the excerpt alone:\n{excerpt[:2000]}\n" if excerpt.strip() else ""
    )
    return f"""A student keeps failing this flashcard, so they have memorised its
wording rather than the material.

Existing question: {question}
Existing answer: {answer}

Write ONE different flashcard that tests the same underlying concept from
another angle. Use different wording, and prefer a different facet of the
concept. Do not restate the existing question.
{grounding}
{ANSWER_RULES}

{WRITING_STYLE}

Return ONLY valid JSON:
{{"question": "...", "answer": "...", "explanation": "...", "difficulty": "easy|medium|hard"}}
"""


def _clean(payload: dict) -> dict | None:
    """Validate a model payload into a card, or None if it is unusable."""
    if not isinstance(payload, dict):
        return None
    question = tidy_question(str(payload.get("question") or ""))
    answer = str(payload.get("answer") or "").strip()
    if not question or not answer:
        return None
    difficulty = str(payload.get("difficulty") or "medium").strip().lower()
    if difficulty not in ("easy", "medium", "hard"):
        difficulty = "medium"
    explanation = tidy_prose(str(payload.get("explanation") or ""))
    return {"question": question, "answer": answer, "explanation": explanation,
            "difficulty": difficulty}


def reformat_fallback(question: str, answer: str) -> dict | None:
    """Turn the card around without a model: ask for the term, given its meaning.

    Deliberately deterministic. It cannot invent a new angle, but it always
    changes what the learner is asked to produce, which is enough to stop a
    memorised string from scoring.
    """
    question, answer = (question or "").strip(), (answer or "").strip()
    if len(answer) < MIN_REFORMAT_CHARS:
        return None
    # \w matches '_', so a question that is itself a previous cloze (ending in
    # the "(______)" blank) would otherwise hand back the blank as the "term" —
    # a card whose answer is literally "______". Drop underscore-only tokens.
    subject = [w for w in _WORD.findall(question) if w.strip("_")]
    term = subject[-1] if subject else ""
    if not term:
        return None
    return {
        "question": f"{answer.rstrip('.')}. Which term does this describe? ({BLANK})",
        "answer": term.capitalize(),
        "difficulty": "medium",
    }


def generate_variant(question: str, answer: str, provider,
                     excerpt: str = "") -> dict | None:
    """A new question on the same concept, or None to keep the original.

    Tries the provider twice — a model that echoes the original once will often
    comply when told plainly — then falls back to a deterministic reformat.
    Returning None is a valid outcome: the card simply stays as it is and is
    retried next time, which is why nothing here raises.
    """
    original_key = _normalize(question)
    prompt = build_variant_prompt(question, answer, excerpt)

    for attempt in range(2):
        text = prompt if attempt == 0 else (
            prompt + "\nYour previous answer repeated the existing question. "
                     "Ask about a different aspect of the concept."
        )
        try:
            card = _clean(provider.generate_json(text))
        except Exception:
            card = None
        if card and _normalize(card["question"]) != original_key:
            return card

    # The fallback is deterministic in (question, answer), so if this card is
    # itself a previous fallback's output — or otherwise already shaped like
    # one — reformatting it again can reproduce the very question the learner
    # is failing. Apply the same dedupe guard used for the LLM path rather
    # than handing back a duplicate.
    fallback = reformat_fallback(question, answer)
    if fallback and _normalize(fallback["question"]) != original_key:
        return fallback
    return None
