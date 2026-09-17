"""One normalisation for extracted document text.

PDFs typeset "fi" and "fl" as single ligature glyphs and pypdf hands them over
unchanged, so "ﬁnancial" is not "financial" to a search, an exact-match
grader, or TF-IDF. NFKC folds ligatures, full-width forms and non-breaking
spaces into their plain equivalents. Applied once, at ingest, so every reader
downstream sees the same text. No Django imports: unit-tested in isolation.
"""
from __future__ import annotations

import unicodedata


def normalise_text(text: str | None) -> str:
    return unicodedata.normalize("NFKC", text or "")
