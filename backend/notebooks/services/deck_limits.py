"""How large one flashcard generation is.

Generating from a document replaces that document's deck rather than adding to
it, so this is a per-generation size rather than a lifetime ceiling: pressing
generate twice leaves ten cards, not twenty, and a document can be refreshed as
often as the learner likes. No Django imports, so the arithmetic is
unit-testable on its own.
"""
from __future__ import annotations

#: Cards one generation produces for a source selection. Ten is a sitting's
#: worth, and — because generating replaces — also the most a selection holds.
MAX_CARDS_PER_SOURCE = 10

#: Below this a deck is too thin to be worth studying, so a smaller request is
#: raised rather than honoured.
MIN_CARDS_PER_SOURCE = 3


def batch_size(requested: int, maximum: int = MAX_CARDS_PER_SOURCE,
               minimum: int = MIN_CARDS_PER_SOURCE) -> int:
    """How many cards to ask a generator for.

    Bounded on both ends, and deliberately independent of how many cards the
    document already holds: that deck is retired by this generation, so
    counting it would shrink the very batch replacing it.
    """
    return max(min(minimum, maximum), min(requested, maximum))
