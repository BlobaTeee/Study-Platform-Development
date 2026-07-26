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

#: Some cards cannot be regenerated at all — a one-word answer leaves the
#: deterministic fallback nothing to reshape, and the model may keep restating
#: the original. Without a ceiling such a card stays flagged forever, burning
#: provider calls on every fetch and starving the slots ahead of cards that
#: could have been replaced. Grading it Hard again resets the count.
MAX_REGENERATION_ATTEMPTS = 3

#: A study page must never block on the model. The per-fetch count cap alone
#: does not bound wall-clock time — a provider timing out on each attempt could
#: hold the request for minutes — so regeneration also stops once this budget
#: is spent, leaving the rest for the next fetch.
REGENERATION_TIME_BUDGET_SECONDS = 15


def select_for_regeneration(cards: list[dict], limit: int) -> list[dict]:
    """The flagged, currently-due cards to regenerate on this fetch.

    New cards are excluded: a card never studied has no memorised wording to
    escape, so spending a model call on it buys nothing. Cards that have
    already exhausted their attempts are excluded too, so one unregenerable
    card cannot occupy a slot on every fetch forever.
    """
    flagged = [
        c for c in cards
        if c.get("needs_regeneration")
        and c.get("status") == "due"
        and (c.get("regeneration_attempts") or 0) < MAX_REGENERATION_ATTEMPTS
    ]
    return flagged[:limit]


def record_failed_attempt(card) -> None:
    """Count a regeneration that produced nothing, and give up at the ceiling.

    Clearing the flag on the last attempt is what stops the card being picked
    again; it stays as it is, which is the honest outcome when no different
    question could be produced for it.
    """
    card.regeneration_attempts = (card.regeneration_attempts or 0) + 1
    fields = ['regeneration_attempts']
    if card.regeneration_attempts >= MAX_REGENERATION_ATTEMPTS:
        card.needs_regeneration = False
        fields.append('needs_regeneration')
    card.save(update_fields=fields)


def replace_card(card, variant: dict):
    """Archive `card` and return its replacement, carrying the schedule over.

    The variant must inherit the original's next-review date, or a card the
    learner just failed would silently leave the queue. The seed review is
    marked `is_seed` so it schedules without counting as a recall.
    """
    from django.db import transaction
    from django.utils import timezone
    from flashcards.models import Flashcard
    from study_sessions.models import CardReview

    # All three writes must land together: a crash between them would leave a
    # replacement with no seed review (so it loses its inherited urgency) or
    # an original that stays active and flagged (so the next fetch regenerates
    # it again, piling up duplicates every time). Atomic makes a partial swap
    # impossible instead of merely unlikely.
    with transaction.atomic():
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
        # when it is next due, so `.grades()` (which excludes seeds) would
        # wrongly skip straight to a card's last real grade instead of its
        # live schedule. The ordering is spelled out rather than inherited from
        # Meta: reordering that default would otherwise hand every replacement
        # its *oldest* schedule, mis-scheduling silently and permanently.
        previous = (CardReview.objects.filter(user=card.user, flashcard=card)
                    .order_by('-review_date').first())
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


def merge_replacements(ranked: list[dict], replacements: dict[int, dict]) -> list[dict]:
    """`ranked` with each entry swapped for its replacement, order preserved.

    Pulled out of the view so the response-shape logic — the part that
    actually risks drifting between originals and replacements — can be unit
    tested without a database.
    """
    return [replacements.get(entry["id"], entry) for entry in ranked]
