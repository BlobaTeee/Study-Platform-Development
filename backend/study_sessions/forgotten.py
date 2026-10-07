"""The cards a student is forgetting right now, grouped by concept.

A card is forgotten while its newest review says so: a "hard" grade, or the
seed row of a variant — variants are only written for a card just failed,
so the seed carries that failure until the variant itself is answered.

Grouping is done twice. The weak-concepts clusters (TF-IDF, no model) catch
cards that share their words. Cards on one idea worded differently — "direct
action features", "emotional goals in requirements", "emotion-led design" —
share almost none, so whatever the clusters leave is grouped by the model,
which reads meaning. Every card ends in a named group, so every one can be
relearned and explained; without a model each leftover stands alone.
"""
import hashlib
import logging

from django.core.cache import cache

from ml_pipeline.weak_concepts import cluster_questions, top_terms
from notebooks.services.ai_provider import get_ai_provider
from quizzes.services.concepts import LABEL_TTL, _label

from notebooks.models import Notebook

from .models import CardReview

logger = logging.getLogger(__name__)

FORGOTTEN_RESULTS = {'hard', 'seed'}
MAX_LEFTOVERS_FOR_MODEL = 40   # a prompt the model can still read whole


REMEMBERED_RESULTS = {'good', 'easy'}


def newest_results(user, cards) -> dict[int, str]:
    """card id -> the result of `user`'s newest review of it. Cards never
    reviewed are absent. `cards` is a Flashcard queryset or a list of ids."""
    newest: dict[int, tuple] = {}
    rows = (CardReview.objects.filter(user=user, flashcard__in=cards)
            .latest_per_card().values_list('flashcard_id', 'review_date', 'result'))
    for card_id, when, result in rows:
        if card_id not in newest or when > newest[card_id][0]:
            newest[card_id] = (when, result)
    return {i: result for i, (_, result) in newest.items()}


def remembered_ids(user, cards) -> set[int]:
    """The cards whose newest grade says the student knew them."""
    return {i for i, r in newest_results(user, cards).items() if r in REMEMBERED_RESULTS}


def forgotten_cards(user, cards) -> list:
    """The subset of `cards` (a Flashcard queryset) whose newest review by
    `user` is a failure, oldest card first."""
    ids = [i for i, r in newest_results(user, cards).items() if r in FORGOTTEN_RESULTS]
    return list(cards.filter(id__in=ids).order_by('id'))


def forgotten_by_notebook(user, cards) -> list[dict]:
    """One entry per notebook, the one with most forgotten cards first:
    {notebook_id, title, count, card_ids, groups}.

    Listed flat, every notebook's groups piled into one long list, subjects
    mixed. Grouped here they stay one short line per notebook, and a concept
    is only ever looked for within one subject's cards."""
    by_notebook: dict = {}
    for card in forgotten_cards(user, cards):
        by_notebook.setdefault(card.notebook_id, []).append(card)
    titles = dict(Notebook.objects.filter(id__in=[i for i in by_notebook if i])
                  .values_list('id', 'title'))
    out = [{
        'notebook_id': nb_id,
        'title': titles.get(nb_id, ''),
        'count': len(members),
        'card_ids': [c.id for c in members],
        'groups': _concept_groups(members),
    } for nb_id, members in by_notebook.items()]
    return sorted(out, key=lambda nb: (-nb['count'], nb['title']))


def _concept_groups(cards: list) -> list[dict]:
    """Groups biggest first: {key, label, card_ids, count, sample}."""
    texts = [f'{c.question} {c.answer}' for c in cards]
    plain = [c.question for c in cards]
    groups, grouped = [], set()
    for cluster in cluster_questions(texts):
        members = [cards[i] for i in cluster.indices]
        grouped.update(cluster.indices)
        key = _key(members)
        groups.append(_group(key, members, _label(key, [c.question for c in members],
                                                  top_terms(plain, cluster.indices))))
    rest = [c for i, c in enumerate(cards) if i not in grouped]
    groups.extend(_group(_key(members), members, label) for label, members in _by_meaning(rest))
    return sorted(groups, key=lambda g: -g['count'])


def _by_meaning(cards) -> list[tuple[str, list]]:
    """(label, cards) for cards the word clusters left out."""
    if not cards:
        return []
    cache_key = f'forgotten-meaning:{_key(cards)}'
    cached = cache.get(cache_key)
    if cached is None:
        cached = _ask_model(cards) if len(cards) > 1 else []
        # A failure is not remembered: the next load asks again.
        if cached is not None:
            cache.set(cache_key, cached, LABEL_TTL)
    by_id = {c.id: c for c in cards}
    out, placed = [], set()
    for label, ids in cached or []:
        members = [by_id[i] for i in ids if i in by_id and i not in placed]
        if members:
            placed.update(c.id for c in members)
            out.append((label or _own_words(members[0]), members))
    # Anything the model dropped, and everything when there is no model.
    out.extend((_own_words(c), [c]) for c in cards if c.id not in placed)
    return out


def _ask_model(cards) -> list[tuple[str, list[int]]] | None:
    shown = cards[:MAX_LEFTOVERS_FOR_MODEL]
    listed = '\n'.join(f'{i}. {c.question} — {c.answer}' for i, c in enumerate(shown, 1))
    prompt = f"""A student keeps forgetting these flashcards. Group them by the concept they test:
cards about the same idea go together even when worded differently; a card unlike the
others stands alone. Name each group in 2 to 5 words, in the language of the cards —
a noun phrase, no quotes, no trailing period. Use every card number exactly once.

{listed}

Return ONLY valid JSON: {{"groups": [{{"label": "...", "cards": [1, 2]}}]}}"""
    try:
        data = get_ai_provider().generate_json(prompt)
    except Exception as exc:  # noqa: BLE001 — no provider, quota, bad JSON: each card stands alone
        logger.info('Grouping forgotten cards fell back to one per card: %s', exc)
        return None
    out = []
    for g in data.get('groups') or [] if isinstance(data, dict) else []:
        if not isinstance(g, dict) or not isinstance(g.get('cards'), list):
            continue
        ids = [shown[n - 1].id for n in g['cards']
               if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= len(shown)]
        label = str(g.get('label') or '').strip().strip('."\'')[:80]
        if ids:
            out.append((label, ids))
    return out


def _own_words(card) -> str:
    """A name for a card that stands alone: its question, kept short."""
    words = card.question.replace('___', '…').split()
    return ' '.join(words[:8]) + ('…' if len(words) > 8 else '')


def _key(members) -> str:
    # Prefixed so a card group never shares a cached name with a question
    # group that happens to have the same ids.
    ids = sorted(c.id for c in members)
    return hashlib.sha1(('cards:' + ','.join(map(str, ids))).encode()).hexdigest()[:12]


def _group(key, members, label) -> dict:
    return {
        'key': key,
        'label': label,
        'card_ids': [c.id for c in members],
        'count': len(members),
        'sample': members[0].question,
    }
