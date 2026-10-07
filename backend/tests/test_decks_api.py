"""A deck is the cards generated from exactly one selection of sources.

The workspace counts it and generation adds to it; both must draw the same
line, and neither may treat a superset as the same deck. (Adding rather than
replacing is covered in test_add_more_cards.)"""
import pytest

from flashcards.models import Flashcard
from notebooks.services.generate import _attach_deck
from quizzes.models import Quiz

pytestmark = pytest.mark.django_db


def _cards(user, n, sources=(), notebook=None):
    cards = [Flashcard.objects.create(user=user, notebook=notebook,
                                      question=f'q{i}', answer='a') for i in range(n)]
    for card in cards:
        card.sources.set(sources)
    return cards


def _counts(client, notebook, sources):
    ids = ','.join(str(s.id) for s in sources)
    return client.get(f'/api/notebooks/notebooks/{notebook.id}/material_counts/?source_ids={ids}').json()


# ---- material_counts ---------------------------------------------------------

def test_counts_the_deck_for_exactly_that_selection(client, user, notebook):
    cells, genetics = notebook.sources.order_by('id')
    _cards(user, 3, [cells], notebook)
    _cards(user, 2, [cells, genetics], notebook)

    assert _counts(client, notebook, [cells])['flashcards'] == 3
    assert _counts(client, notebook, [cells, genetics])['flashcards'] == 2
    assert _counts(client, notebook, [genetics])['flashcards'] == 0


def test_archived_cards_are_not_counted(client, user, notebook):
    cells, _ = notebook.sources.order_by('id')
    live = _cards(user, 2, [cells], notebook)
    Flashcard.objects.filter(id=live[0].id).update(archived=True)

    assert _counts(client, notebook, [cells])['flashcards'] == 1


def test_reports_the_newest_quiz_for_that_exact_selection(client, user, notebook):
    cells, genetics = notebook.sources.order_by('id')
    older = Quiz.objects.create(user=user, title='old', is_published=True); older.sources.set([cells])
    newer = Quiz.objects.create(user=user, title='new', is_published=True); newer.sources.set([cells])
    both = Quiz.objects.create(user=user, title='both', is_published=True); both.sources.set([cells, genetics])

    assert _counts(client, notebook, [cells])['quiz_id'] == newer.id
    assert _counts(client, notebook, [cells, genetics])['quiz_id'] == both.id
    assert _counts(client, notebook, [genetics])['quiz_id'] is None


def test_another_users_notebook_is_not_found(client, other_user, notebook):
    from notebooks.models import Notebook
    theirs = Notebook.objects.create(user=other_user, title='Theirs')
    res = client.get(f'/api/notebooks/notebooks/{theirs.id}/material_counts/?source_ids=1')
    assert res.status_code == 404


# ---- _attach_deck ------------------------------------------------------------

def test_a_new_batch_gets_its_sources_and_notebook(user, notebook):
    cells, genetics = notebook.sources.order_by('id')
    cards = _cards(user, 2)

    _attach_deck(cards, [cells.id, genetics.id], notebook)

    for card in cards:
        card.refresh_from_db()
        assert set(card.sources.values_list('id', flat=True)) == {cells.id, genetics.id}
        assert card.notebook_id == notebook.id


def test_attaching_a_batch_never_retires_another(user, notebook):
    cells, genetics = notebook.sources.order_by('id')
    first = _cards(user, 2)
    _attach_deck(first, [cells.id], notebook)

    _attach_deck(_cards(user, 2), [cells.id], notebook)

    assert not Flashcard.objects.filter(id__in=[c.id for c in first], archived=True).exists()
