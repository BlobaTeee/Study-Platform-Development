"""How large one flashcard generation is.

Generating adds a batch to a document's deck. This is the size of one batch,
and also the most a document may hold unstarted: while that many of its cards
were never studied, it gets no more. No Django imports, so the arithmetic is
unit-testable on its own.
"""
from __future__ import annotations

#: Cards one generation produces for a source selection. Ten is a sitting's
#: worth, and also the most a selection may hold unstarted.
MAX_CARDS_PER_SOURCE = 10

#: Below this a deck is too thin to be worth studying, so a smaller request is
#: raised rather than honoured.
MIN_CARDS_PER_SOURCE = 3


def batch_size(requested: int, maximum: int = MAX_CARDS_PER_SOURCE,
               minimum: int = MIN_CARDS_PER_SOURCE) -> int:
    """How many cards to ask a generator for.

    Bounded on both ends. Whether a batch may be added at all is decided by
    the caller, from how many of the deck's cards are still unstarted.
    """
    return max(min(minimum, maximum), min(requested, maximum))
