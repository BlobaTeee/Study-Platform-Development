"""Study insights derived from the user's own cards and performance.

Replaces the old fixed-taxonomy recommender, which could only suggest subjects
from a 5-subject STEM list and so returned irrelevant topics for real uploaded
documents. Everything here is computed from the user's actual review history.

No Django imports: views pass ORM data in as plain dicts, so this stays
unit-testable in isolation.
"""
from __future__ import annotations

SOURCE_TAG_PREFIX = "source:"


def card_priority(correct: int, incorrect: int) -> float:
    """How urgently a card needs reviewing, in (0, 1) — higher means sooner.

    Laplace-smoothed error rate, which handles all three cases with one formula:
    often-wrong cards score high, never-reviewed cards land at 0.5 (unknown
    mastery, worth testing), and reliably-correct cards score low.
    """
    return (incorrect + 1) / (correct + incorrect + 2)


def rank_weak_cards(cards: list[dict], limit: int) -> list[dict]:
    """The `limit` cards most worth reviewing, weakest first."""
    scored = [
        {
            "id": c["id"],
            "question": c.get("question", ""),
            "correct_count": c.get("correct_count", 0),
            "incorrect_count": c.get("incorrect_count", 0),
            "priority": round(
                card_priority(c.get("correct_count", 0), c.get("incorrect_count", 0)), 4
            ),
        }
        for c in cards
    ]
    # Sort by id first so equal priorities keep a stable, predictable order.
    scored.sort(key=lambda c: c["id"])
    scored.sort(key=lambda c: c["priority"], reverse=True)
    return scored[:limit]


def parse_source_ids(tag: str | None) -> list[int]:
    """Extract source ids from a card tag like ``source:1,2``.

    Cards may be generated from several sources at once. Malformed pieces are
    skipped rather than failing the whole card.
    """
    if not tag or not tag.startswith(SOURCE_TAG_PREFIX):
        return []
    ids = []
    for piece in tag[len(SOURCE_TAG_PREFIX):].split(","):
        piece = piece.strip()
        if piece.isdigit():
            ids.append(int(piece))
    return ids


def per_source_accuracy(cards: list[dict], source_titles: dict[int, str]) -> list[dict]:
    """Accuracy per source document, weakest first.

    `source_titles` maps source id -> title; cards pointing at a source that no
    longer exists are ignored. A document with no reviews reports accuracy None
    rather than 0%, which would wrongly imply the user got it wrong.
    """
    totals: dict[int, dict] = {}
    for card in cards:
        for sid in parse_source_ids(card.get("tags")):
            if sid not in source_titles:
                continue
            bucket = totals.setdefault(sid, {"correct": 0, "incorrect": 0, "cards": 0})
            bucket["correct"] += card.get("correct_count", 0)
            bucket["incorrect"] += card.get("incorrect_count", 0)
            bucket["cards"] += 1

    out = []
    for sid, b in totals.items():
        reviews = b["correct"] + b["incorrect"]
        out.append({
            "source_id": sid,
            "title": source_titles[sid],
            "cards": b["cards"],
            "reviews": reviews,
            "accuracy": round(b["correct"] / reviews * 100, 1) if reviews else None,
        })

    # Weakest first; never-reviewed documents go last (nothing to act on yet).
    out.sort(key=lambda s: (s["accuracy"] is None, s["accuracy"] if s["accuracy"] is not None else 0))
    return out
