"""One normalisation for extracted document text.

PDFs typeset "fi" and "fl" as single ligature glyphs and pypdf hands them over
unchanged, so "ﬁnancial" is not "financial" to a search, an exact-match
grader, or TF-IDF. NFKC folds ligatures, full-width forms and non-breaking
spaces into their plain equivalents. Applied once, at ingest, so every reader
downstream sees the same text. No Django imports: unit-tested in isolation.
"""
from __future__ import annotations

import re
import unicodedata


def normalise_text(text: str | None) -> str:
    return unicodedata.normalize("NFKC", text or "")


# A model asked for an overview sometimes opens with a line about itself —
# "Here is a summary of the study in 2-3 sentences:" — before the overview.
# Only a short lead-in that ends in a colon counts, so an overview that merely
# starts with "Here," or uses a colon later on is left as written.
_PREAMBLE = re.compile(
    r"^\s*(?:(?:sure|certainly|okay|of course)[!.,]?\s+)?"
    r"(?:here is|here's|below is|đây là|dưới đây là)\b[^:\n]{0,120}:\s*",
    re.IGNORECASE,
)


def clean_summary(text: str | None) -> str:
    """The overview without the model's own lead-in, if it wrote one.

    A preamble with nothing after it is returned unchanged rather than
    blanked: an empty overview would hide that something went wrong.
    """
    text = text or ""
    stripped = _PREAMBLE.sub("", text, count=1)
    return stripped if stripped.strip() else text
