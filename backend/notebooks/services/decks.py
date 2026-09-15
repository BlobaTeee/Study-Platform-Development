"""Which items make up "the deck" for a selection of sources.

A deck is everything generated from exactly one selection — the same
documents, no more, no fewer. Regeneration retires the previous deck and the
notebook workspace counts it, so both must agree on what it is.

Computed in Python over (item, source) pairs rather than with chained
many-to-many filters plus an annotate: the ORM's join reuse on multi-valued
relations is exactly the kind of thing that returns a superset without
complaint, and a user's through rows number a few hundred at most.
"""
from __future__ import annotations

from typing import Iterable


def items_with_exact_sources(pairs: Iterable[tuple[int, int]],
                             source_ids: Iterable[int]) -> list[int]:
    """Ids of the items whose linked sources are exactly `source_ids`.

    `pairs` are (item_id, source_id) rows. An item that appears in no pair
    has no sources and can never match; an empty selection matches nothing.
    """
    wanted = set(source_ids)
    if not wanted:
        return []
    by_item: dict[int, set[int]] = {}
    for item_id, source_id in pairs:
        by_item.setdefault(item_id, set()).add(source_id)
    return [item_id for item_id, linked in by_item.items() if linked == wanted]
