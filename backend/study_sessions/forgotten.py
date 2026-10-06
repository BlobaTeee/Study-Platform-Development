"""The cards a student is forgetting right now, grouped by concept.

A card is forgotten while its newest review says so: a "hard" grade, or the
seed row of a variant — variants are only written for a card just failed,
so the seed carries that failure until the variant itself is answered.

Grouping and naming are the weak-concepts ones (TF-IDF clusters, a cached
model-written name); cards that join no cluster are kept together as one
"other" group rather than dropped, since each is still a card to relearn.
"""
import hashlib

from ml_pipeline.weak_concepts import cluster_questions, top_terms
from quizzes.services.concepts import _label

from .models import CardReview

FORGOTTEN_RESULTS = {'hard', 'seed'}


def forgotten_cards(user, cards) -> list:
    """The subset of `cards` (a Flashcard queryset) whose newest review by
    `user` is a failure, oldest card first."""
    newest: dict[int, tuple] = {}
    rows = (CardReview.objects.filter(user=user, flashcard__in=cards)
            .latest_per_card().values_list('flashcard_id', 'review_date', 'result'))
    for card_id, when, result in rows:
        if card_id not in newest or when > newest[card_id][0]:
            newest[card_id] = (when, result)
    ids = [i for i, (_, result) in newest.items() if result in FORGOTTEN_RESULTS]
    return list(cards.filter(id__in=ids).order_by('id'))


def forgotten_groups(user, cards) -> list[dict]:
    """Groups biggest first, then the "other" group last:
    {key, label, card_ids, count, sample, other}."""
    cards = forgotten_cards(user, cards)
    texts = [f'{c.question} {c.answer}' for c in cards]
    plain = [c.question for c in cards]
    groups, grouped = [], set()
    for cluster in cluster_questions(texts):
        members = [cards[i] for i in cluster.indices]
        grouped.update(cluster.indices)
        ids = sorted(c.id for c in members)
        # Prefixed so a card group never shares a cached name with a
        # question group that happens to have the same ids.
        key = hashlib.sha1(('cards:' + ','.join(map(str, ids))).encode()).hexdigest()[:12]
        groups.append(_group(key, members, _label(key, [c.question for c in members],
                                                  top_terms(plain, cluster.indices))))
    rest = [c for i, c in enumerate(cards) if i not in grouped]
    if rest:
        groups.append({**_group('other', rest, ''), 'other': True})
    return groups


def _group(key, members, label) -> dict:
    return {
        'key': key,
        'label': label,
        'card_ids': [c.id for c in members],
        'count': len(members),
        'sample': members[0].question,
        'other': False,
    }
