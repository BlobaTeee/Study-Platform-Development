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
    # Reviewed just now, so it is remembered: strong, and nothing to press.
    assert by['Acids']['state'] == 'strong' and by['Acids']['action'] is None
    assert by['Enzymes']['understanding'] == {'p': pytest.approx(by['Enzymes']['understanding']['p']),
                                              'correct': 0, 'total': 1}
    assert by['Enzymes']['state'] in ('weak', 'shaky')
    assert by['Enzymes']['action'] == {'kind': 'practice', 'question_ids': [q.id]}


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


class Reply:
    def __init__(self, data): self.data = data
    def generate_json(self, prompt):
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


def _links(client, monkeypatch, nb, data):
    monkeypatch.setattr('notebooks.services.knowledge_map.get_ai_provider', lambda: Reply(data))
    return client.post(MAP.format(nb.id) + 'links/')


def test_links_are_cleaned_and_kept(client, monkeypatch, chem):
    nb, src = chem
    res = _links(client, monkeypatch, nb, {'links': [{'before': 1, 'after': 2, 'why': 'Enzymes act on acids'},
                                                     {'before': 2, 'after': 1, 'why': 'loop'},
                                                     {'before': 7, 'after': 1}]})
    assert res.status_code == 200
    assert res.json()['edges'] == [{'from': f'{src.id}:0', 'to': f'{src.id}:1', 'why': 'Enzymes act on acids'}]
    assert client.get(MAP.format(nb.id)).json()['edges_status'] == 'ready'


def test_a_reply_that_is_not_links_is_unavailable_and_saves_nothing(client, monkeypatch, chem):
    nb, _ = chem
    assert _links(client, monkeypatch, nb, {'nonsense': True}).status_code == 503
    assert client.get(MAP.format(nb.id)).json()['edges_status'] == 'missing'


def test_cached_links_are_not_asked_for_again(client, monkeypatch, chem):
    nb, src = chem
    first = _links(client, monkeypatch, nb, {'links': [{'before': 1, 'after': 2, 'why': 'Acids first'}]})
    second = _links(client, monkeypatch, nb, RuntimeError('should not be called'))
    assert second.status_code == 200 and second.json()['edges'] == first.json()['edges'] != []


def test_a_notebook_with_one_concept_has_no_links_to_find(client, monkeypatch, chem):
    nb, src = chem
    src.key_points = src.key_points[:1]
    src.save()
    res = _links(client, monkeypatch, nb, RuntimeError('should not be called'))
    assert res.status_code == 200 and res.json() == {'edges': [], 'edges_status': 'none'}


def test_a_failed_request_is_503_and_the_map_still_loads(client, monkeypatch, chem):
    nb, _ = chem
    assert _links(client, monkeypatch, nb, RuntimeError('429 quota')).status_code == 503
    assert client.get(MAP.format(nb.id)).json()['edges_status'] == 'missing'


def test_practice_needs_a_concept_with_questions(client, chem):
    nb, src = chem
    res = client.post(MAP.format(nb.id) + 'practice/', {'concept': f'{src.id}:0'}, format='json')
    assert res.status_code == 400


@pytest.fixture
def missed(user, chem):
    """Enzymes has a wrong answer, so its action is to practise."""
    nb, src = chem
    quiz = Quiz.objects.create(user=user, title='Q', is_published=True)
    q = Question.objects.create(quiz=quiz, source=src, source_excerpt=ENZ, question_text='What speeds reactions?',
                                question_type='multiple_choice', options=['Enzymes', 'Salt', 'Ice', 'Sand'],
                                correct_answer='Enzymes')
    att = QuizAttempt.objects.create(quiz=quiz, user=user)
    Answer.objects.create(quiz_attempt=att, question=q, user_answer='Salt', is_correct=False)
    return nb, src


def _practice(client, nb, src, monkeypatch, made):
    def fake(user, notebook, label, questions, key=''):
        if isinstance(made, Exception):
            raise made
        quiz = Quiz.objects.create(user=user, title=label, is_published=True, practice_key=key)
        quiz.sources.set([src])
        return quiz
    monkeypatch.setattr('quizzes.services.practice.generate_practice_quiz', fake)
    return client.post(MAP.format(nb.id) + 'practice/', {'concept': f'{src.id}:1'}, format='json')


def test_practice_makes_a_quiz_and_reuses_it_until_finished(client, user, monkeypatch, missed):
    nb, src = missed
    first = _practice(client, nb, src, monkeypatch, None)
    assert first.status_code == 201 and first.json()['source_ids'] == [src.id]
    again = _practice(client, nb, src, monkeypatch, None)
    assert again.status_code == 200 and again.json()['quiz_id'] == first.json()['quiz_id']

    QuizAttempt.objects.create(quiz_id=first.json()['quiz_id'], user=user, is_completed=True)
    fresh = _practice(client, nb, src, monkeypatch, None)
    assert fresh.status_code == 201 and fresh.json()['quiz_id'] != first.json()['quiz_id']


def test_practice_that_cannot_be_made_is_503(client, monkeypatch, missed):
    from quizzes.services.practice import PracticeUnavailable
    nb, src = missed
    assert _practice(client, nb, src, monkeypatch, PracticeUnavailable('no')).status_code == 503


def test_practice_with_a_body_that_is_not_an_object_is_400(client, chem):
    nb, _ = chem
    assert client.post(MAP.format(nb.id) + 'practice/', ['x'], format='json').status_code == 400


def test_the_exercise_offered_is_one_not_yet_mastered(client, user, missed):
    from exercises.models import Exercise
    nb, src = missed
    ref = {'checkpoints': [{'id': 'c1', 'text': 'Enzymes', 'basis': ENZ}]}
    done = Exercise.objects.create(user=user, notebook=nb, source=src, prompt='Why do enzymes speed reactions?',
                                   reference=ref, status='mastered')
    todo = Exercise.objects.create(user=user, notebook=nb, source=src, prompt='How do enzymes speed reactions?',
                                   reference=ref, status='new')

    enzymes = next(c for c in client.get(MAP.format(nb.id)).json()['concepts'] if c['label'] == 'Enzymes')

    assert enzymes['state'] != 'strong'
    assert enzymes['action'] == {'kind': 'exercise', 'exercise_id': todo.id} != {'exercise_id': done.id}


def test_each_concept_says_which_key_points_it_holds(client, chem):
    """So a document can show its own key points' states: 'source:index'."""
    nb, src = chem
    concepts = client.get(MAP.format(nb.id)).json()['concepts']
    assert sorted(m for c in concepts for m in c['members']) == [f'{src.id}:0', f'{src.id}:1']
