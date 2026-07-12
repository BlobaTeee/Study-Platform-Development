"""Flashcard generation from source text (classical, local; no LLM)."""
from __future__ import annotations

from .content_extractor import (
    ContentExtractor, DEFINITIONAL_LABELS, blank_term, difficulty_for,
)

OVERSAMPLE = 3
BLANK = "______"


class FlashcardGenerator:
    def __init__(self, extractor=None):
        self._extractor = extractor

    @property
    def extractor(self):
        return self._extractor if self._extractor is not None else ContentExtractor()

    def generate(self, text: str, count: int, title: str = "") -> list[dict]:
        count = max(0, count)
        if count == 0:
            return []
        candidates = self.extractor.extract_candidates(text, count * OVERSAMPLE)
        cards = []
        for c in candidates:
            if c.label in DEFINITIONAL_LABELS:
                question, answer = f"What is {c.term}?", c.sentence
            else:
                question, answer = blank_term(c.sentence, c.term, BLANK), c.term
            cards.append({"question": question, "answer": answer,
                          "difficulty": difficulty_for(c)})
            if len(cards) >= count:
                break
        return cards
