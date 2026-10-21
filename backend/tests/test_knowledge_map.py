"""The knowledge map: concepts from key points, the student's own signals."""
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
    assert body['edges_status'] == 'missing'
    assert all(c['state'] == 'not_studied' and c['action'] is None for c in body['concepts'])


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
    assert by['Acids']['action'] == {'kind': 'cards', 'card_ids': [card.id]}
    assert by['Enzymes']['understanding'] == {'p': pytest.approx(by['Enzymes']['understanding']['p']),
                                              'correct': 0, 'total': 1}
    assert by['Enzymes']['state'] in ('weak', 'shaky')
    assert by['Enzymes']['action'] == {'kind': 'practice', 'question_ids': [q.id]}


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


def test_cached_links_count_only_for_the_same_concepts(client, chem):
    from notebooks.services.knowledge_map import concepts_hash, concepts_of
    nb, src = chem
    nb.concept_links = {'hash': concepts_hash(concepts_of(nb)),
                        'edges': [{'from': f'{src.id}:0', 'to': f'{src.id}:1', 'why': 'acids first'}]}
    nb.save()
    body = client.get(MAP.format(nb.id)).json()
    assert body['edges_status'] == 'ready' and body['edges'][0]['why'] == 'acids first'
    src.key_points = src.key_points[:1]
    src.save()
    assert client.get(MAP.format(nb.id)).json()['edges_status'] == 'none'
