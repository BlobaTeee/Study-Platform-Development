"""How well each of a notebook's concepts is known, for the key points list:
concepts from key points, the student's own signals. The map views that
were built on this (links, drawing from memory, practising a concept) are gone."""
import pytest

from flashcards.models import Flashcard
from notebooks.models import NotebookMember, Source
from quizzes.models import Answer, Question, Quiz, QuizAttempt
from study_sessions.models import CardReview
from tests.conftest import make_source

pytestmark = pytest.mark.django_db
MAP = '/api/notebooks/notebooks/{}/map/'
ACID = 'An acid donates a proton to a base when the two react in water.'
ENZ = 'Enzymes are proteins that speed up chemical reactions in cells.'


@pytest.fixture
def chem(user):
    from notebooks.models import Notebook
    nb = Notebook.objects.create(user=user, title='Chemistry')
    src = make_source(nb, 'Reactions', (ACID + ' ' + ENZ + ' ') * 30)
    src.key_points = [{'point': 'Acids donate protons', 'label': 'Acids', 'importance': 'core', 'passage': ACID},
                      {'point': 'Enzymes speed reactions', 'label': 'Enzymes', 'importance': 'core', 'passage': ENZ}]
    src.save()
    make_source(nb, 'Notes')                          # no key points yet
    return nb, src


def _card(user, nb, src, q, a):
    card = Flashcard.objects.create(user=user, notebook=nb, question=q, answer=a)
    card.sources.set([src])
    return card


def test_concepts_come_from_key_points_and_documents_without_them_are_named(client, chem):
    nb, src = chem
    body = client.get(MAP.format(nb.id)).json()
    assert [c['label'] for c in body['concepts']] == ['Acids', 'Enzymes']
    assert [m['title'] for m in body['missing_key_points']] == ['Notes']
    assert all(c['state'] == 'not_studied' for c in body['concepts'])
    assert 'edges' not in body and all('action' not in c for c in body['concepts'])


def test_cards_give_memory_and_answers_give_understanding(client, user, chem):
    nb, src = chem
    card = _card(user, nb, src, 'What does an acid donate to a base?', 'A proton')
    CardReview.record(user, card, 'good')
    quiz = Quiz.objects.create(user=user, title='Q', is_published=True)
    q = Question.objects.create(quiz=quiz, source=src, source_excerpt=ENZ, question_text='What speeds reactions?',
                                question_type='multiple_choice', options=['Enzymes', 'Salt', 'Ice', 'Sand'],
                                correct_answer='Enzymes')
    att = QuizAttempt.objects.create(quiz=quiz, user=user)
    Answer.objects.create(quiz_attempt=att, question=q, user_answer='Salt', is_correct=False)

    by = {c['label']: c for c in client.get(MAP.format(nb.id)).json()['concepts']}

    assert by['Acids']['memory']['total'] == 1 and by['Acids']['understanding'] is None
    # Reviewed just now, so it is remembered: strong.
    assert by['Acids']['state'] == 'strong'
    assert by['Enzymes']['understanding'] == {'p': pytest.approx(by['Enzymes']['understanding']['p']),
                                              'correct': 0, 'total': 1}
    assert by['Enzymes']['state'] in ('weak', 'shaky')


ACID_CARDS = [('What does an acid donate to a base?', 'A proton'), ('What does an acid give a base in water?', 'A proton'),
              ('An acid reacts with a base by donating what?', 'A proton'), ('Which donates a proton, acid or base?', 'An acid'),
              ('What accepts the proton an acid donates?', 'A base'), ('Where do an acid and a base react?', 'In water')]


def test_memory_counts_reviewed_cards_and_names_the_unseen(client, user, chem):
    nb, src = chem
    cards = [_card(user, nb, src, q, a) for q, a in ACID_CARDS]
    for card in cards[:2]:
        CardReview.record(user, card, 'good')

    acids = next(c for c in client.get(MAP.format(nb.id)).json()['concepts'] if c['label'] == 'Acids')

    assert acids['memory']['total'] == 2 and acids['memory']['unseen'] == 4
    assert acids['memory']['remembered'] <= acids['memory']['total']


def test_events_count_every_review_not_every_card(client, user, chem):
    nb, src = chem
    card = _card(user, nb, src, *ACID_CARDS[0])
    for _ in range(5):
        CardReview.record(user, card, 'good')

    acids = next(c for c in client.get(MAP.format(nb.id)).json()['concepts'] if c['label'] == 'Acids')

    assert acids['events'] == 5


def test_a_member_sees_their_own_mastery(client, other_client, user, other_user, chem):
    nb, src = chem
    NotebookMember.objects.create(notebook=nb, user=other_user, role='member')
    card = _card(user, nb, src, 'What does an acid donate?', 'A proton')
    CardReview.record(user, card, 'good')

    theirs = {c['label']: c for c in other_client.get(MAP.format(nb.id)).json()['concepts']}

    assert theirs['Acids']['memory'] is None and theirs['Acids']['state'] == 'not_studied'


def test_a_stranger_gets_404(other_client, chem):
    nb, _ = chem
    assert other_client.get(MAP.format(nb.id)).status_code == 404


@pytest.mark.parametrize('path', ['links/', 'build/', 'practice/'])
def test_the_map_views_are_gone(client, chem, path):
    nb, _ = chem
    assert client.post(MAP.format(nb.id) + path, {}, format='json').status_code == 404


def test_each_concept_says_which_key_points_it_holds(client, chem):
    """So a document can show its own key points' states: 'source:index'."""
    nb, src = chem
    concepts = client.get(MAP.format(nb.id)).json()['concepts']
    assert sorted(m for c in concepts for m in c['members']) == [f'{src.id}:0', f'{src.id}:1']
