"""Lightweight text descriptors for exploratory data analysis."""
from __future__ import annotations

import re

import textstat

_SENTENCE_SPLIT = re.compile(r"[.!?]+")


def _sentence_count(text: str) -> int:
    """Deterministic sentence count (textstat under-counts short sentences)."""
    return sum(1 for part in _SENTENCE_SPLIT.split(text) if part.strip())


def text_stats(text: str) -> dict:
    """Return basic length/readability stats for a piece of text."""
    text = text or ""
    tokens = text.split()
    if not tokens:
        return {"n_chars": 0, "n_tokens": 0, "n_sentences": 0,
                "flesch_reading_ease": 0.0}
    return {
        "n_chars": len(text),
        "n_tokens": len(tokens),
        "n_sentences": max(1, _sentence_count(text)),
        "flesch_reading_ease": float(textstat.flesch_reading_ease(text)),
    }
