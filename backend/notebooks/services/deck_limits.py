"""How many more flashcards a document may hold.

Generating appends, and dedupe only rejects questions the document already
asks, so without a ceiling a document generated from three times carries thirty
cards and the learner's queue fills with one subject. No Django imports, so the
arithmetic is unit-testable on its own.
"""
from __future__ import annotations

#: Active cards a single source selection may hold. Ten is a sitting's worth.
MAX_CARDS_PER_SOURCE = 10


def room_for(existing_active: int, maximum: int = MAX_CARDS_PER_SOURCE) -> int:
    """How many cards may still be added. Never negative.

    Counts active cards only: regeneration archives a card and adds its
    replacement, so a document that refreshes a failed card stays at its cap
    rather than creeping past it.
    """
    return max(0, maximum - existing_active)


def capped_count(requested: int, existing_active: int, maximum: int = MAX_CARDS_PER_SOURCE) -> int:
    """How many cards it is safe to ask a generator for.

    Bounds `requested` to the room actually left on the document: never more
    than that room, never negative. Callers must apply this before branching
    into any generator, because some generators (ML-primary, local fallback)
    create rows directly and never pass back through a save-step ceiling.
    """
    return max(0, min(requested, room_for(existing_active, maximum)))
