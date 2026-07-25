"""Replacing a failed flashcard with a fresh question on the same concept.

Split in two. `select_for_regeneration` is a pure policy — which flagged cards
are worth the model calls on this fetch — and is unit-tested without a database.
`replace_card` performs the swap and needs Django, so it is kept deliberately
small.
"""
from __future__ import annotations

#: Model calls are seconds each, and a due-fetch blocks the study page, so a
#: backlog is worked through a few cards at a time rather than all at once.
MAX_REGENERATIONS_PER_FETCH = 3


def select_for_regeneration(cards: list[dict], limit: int) -> list[dict]:
    """The flagged, currently-due cards to regenerate on this fetch.

    New cards are excluded: a card never studied has no memorised wording to
    escape, so spending a model call on it buys nothing.
    """
    flagged = [c for c in cards
               if c.get("needs_regeneration") and c.get("status") == "due"]
    return flagged[:limit]


def replace_card(card, variant: dict, generation_source: str = ""):
    """Archive `card` and return its replacement, carrying the schedule over.

    The variant must inherit the original's next-review date, or a card the
    learner just failed would silently leave the queue. The seed review is
    marked `is_seed` so it schedules without counting as a recall.
    """
    from django.utils import timezone
    from flashcards.models import Flashcard
    from study_sessions.models import CardReview

    replacement = Flashcard.objects.create(
        user=card.user,
        topic=card.topic,
        question=variant["question"],
        answer=variant["answer"],
        difficulty=variant.get("difficulty", "medium"),
        tags=card.tags,
        is_public=False,
        origin=card,
        generation=card.generation + 1,
    )

    # Unfiltered on purpose: a seed row is exactly what tells a replacement
    # when it is next due, so `.grades()` (which excludes seeds) would wrongly
    # skip straight to a card's last real grade instead of its live schedule.
    previous = CardReview.objects.filter(user=card.user, flashcard=card).first()
    CardReview.objects.create(
        user=card.user,
        flashcard=replacement,
        result="seed",
        is_seed=True,
        interval=previous.interval if previous else 1,
        ease_factor=previous.ease_factor if previous else 2.5,
        repetitions=previous.repetitions if previous else 0,
        next_review_date=(previous.next_review_date if previous
                          else timezone.localdate()),
    )

    card.archived = True
    card.needs_regeneration = False
    card.save(update_fields=['archived', 'needs_regeneration'])
    return replacement
