"""Split a source document into chunks and pick the most informative ones.

Generating from one giant prompt makes small local models lose the plot (and
silently truncates long documents). Chunking lets generation cover the whole
document with prompts small enough for a 3B model to handle reliably.

Sentence splitting is regex-based rather than spaCy: this runs per request and
only needs boundaries, not linguistic analysis.
"""
from __future__ import annotations

import re

DEFAULT_TARGET_CHARS = 1200
DEFAULT_OVERLAP_SENTENCES = 1

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text.strip()) if s.strip()]


def chunk_text(text: str, target_chars: int = DEFAULT_TARGET_CHARS,
               overlap_sentences: int = DEFAULT_OVERLAP_SENTENCES) -> list[str]:
    """Split `text` into sentence-aligned chunks of roughly `target_chars`.

    Chunks never cut mid-sentence. `overlap_sentences` repeats trailing
    sentences at the start of the next chunk so context isn't lost at seams.
    A single sentence longer than the target is kept whole rather than dropped.
    """
    sents = _sentences(text or "")
    if not sents:
        return []

    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for sent in sents:
        # +1 for the joining space; always keep at least one sentence per chunk
        # so an over-long sentence is emitted rather than discarded.
        if current and size + len(sent) + 1 > target_chars:
            chunks.append(" ".join(current))
            current = current[-overlap_sentences:] if overlap_sentences > 0 else []
            size = sum(len(s) + 1 for s in current)
        current.append(sent)
        size += len(sent) + 1

    if current:
        chunks.append(" ".join(current))
    return chunks


def select_chunks(chunks: list[str], k: int) -> list[str]:
    """Return the `k` most informative chunks, in original document order.

    Ranks by summed TF-IDF weight (a chunk dense in distinctive terms carries
    more teachable content than filler), then restores document order so the
    generated material follows the document's flow.
    """
    if k <= 0 or not chunks:
        return []
    if len(chunks) <= k:
        return list(chunks)

    from sklearn.feature_extraction.text import TfidfVectorizer
    try:
        matrix = TfidfVectorizer(stop_words="english").fit_transform(chunks)
    except ValueError:
        return list(chunks[:k])  # empty vocabulary (e.g. all stopwords)

    salience = matrix.sum(axis=1).A.ravel()
    top = sorted(range(len(chunks)), key=lambda i: (-salience[i], i))[:k]
    return [chunks[i] for i in sorted(top)]
