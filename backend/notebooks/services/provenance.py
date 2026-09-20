"""Which source a generated item's passage came from, and what to keep of it.

Generation works on the sources' text joined together; an item is produced
from one chunk of that. The chunk is what the student should reread, and
the source it sits in is where the reread happens. Django-free.
"""
from __future__ import annotations

import re

_WS = re.compile(r"\s+")
EXCERPT_LIMIT = 1500


def _fold(text: str) -> str:
    return _WS.sub(" ", (text or "")).strip().lower()


def source_of(passage: str, sources: list[tuple[int, str]]) -> int | None:
    """The id of the one source whose text contains `passage`, else None.

    None also when two sources contain it (nothing to choose between) or
    when the passage straddles a boundary (in neither). Whitespace and case
    are folded so a chunk that re-wrapped lines still matches.
    """
    needle = _fold(passage)
    if not needle:
        return None
    hits = [sid for sid, text in sources if needle in _fold(text)]
    return hits[0] if len(hits) == 1 else None


def excerpt_of(passage: str, limit: int = EXCERPT_LIMIT) -> str:
    """`passage` cut to `limit` characters on a sentence end where possible."""
    text = (passage or "").strip()
    if len(text) <= limit:
        return text
    head = text[:limit]
    cut = max(head.rfind(". "), head.rfind(".\n"), head.rfind("!"), head.rfind("?"))
    return head[: cut + 1] if cut > limit // 2 else head.rstrip()
