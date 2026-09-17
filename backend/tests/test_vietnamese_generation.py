"""Generated content follows the language of the source, and a Vietnamese
source never falls through to the English-only extractive pipeline."""
import pytest

from flashcards.models import Flashcard
from notebooks.models import Notebook
from tests.conftest import make_source

pytestmark = pytest.mark.django_db

VI_TEXT = ' '.join(
    'Quang hợp là quá trình thực vật hấp thụ khí carbon dioxide và nước, dùng năng lượng '
    'ánh sáng để tạo ra glucose và giải phóng oxy. Diệp lục trong lá hấp thụ ánh sáng.'
    for _ in range(6))
EN_TEXT = ' '.join(
    'Photosynthesis is the process by which plants absorb carbon dioxide and water and '
    'use light energy to make glucose, releasing oxygen. Chlorophyll absorbs the light.'
    for _ in range(6))


class _CapturingProvider:
    name = 'stub'
    def __init__(self):
        self.prompts = []
    def generate_json(self, prompt):
        self.prompts.append(prompt)
        return {'flashcards': [{'question': 'Q?', 'answer': 'A', 'difficulty': 'easy'}] * 3,
                'questions': [{'question_text': 'Q?', 'correct_answer': 'A',
                               'distractors': ['B', 'C', 'D'], 'explanation': 'E'}] * 4}
    def summarize(self, text, title=''):
        return ''


@pytest.fixture
def vi_notebook(user):
    nb = Notebook.objects.create(user=user, title='Sinh học')
    make_source(nb, 'Quang hợp', VI_TEXT)
    return nb


def _generate(client, notebook, what='flashcards'):
    ids = list(notebook.sources.values_list('id', flat=True))
    return client.post(f'/api/notebooks/notebooks/{notebook.id}/generate_{what}/',
                       {'source_ids': ids}, format='json')


def test_the_prompt_names_the_sources_language(client, vi_notebook, notebook, monkeypatch):
    provider = _CapturingProvider()
    monkeypatch.setattr('notebooks.services.generate.get_ai_provider', lambda: provider)

    assert _generate(client, vi_notebook).status_code == 201
    assert 'Write in Vietnamese' in provider.prompts[-1]

    assert _generate(client, notebook).status_code == 201     # the English fixture
    assert 'Write in English' in provider.prompts[-1]


def test_quiz_prompt_names_the_language_too(client, vi_notebook, monkeypatch):
    provider = _CapturingProvider()
    monkeypatch.setattr('notebooks.services.generate.get_ai_provider', lambda: provider)
    assert _generate(client, vi_notebook, 'quiz').status_code == 201
    assert 'Write in Vietnamese' in provider.prompts[-1]


def test_a_vietnamese_source_with_no_provider_gets_an_honest_error_not_junk(client, vi_notebook, settings):
    # conftest stubs the provider to fail; with the local fallback on, an
    # English source would get extractive cards — a Vietnamese one must not.
    settings.USE_LOCAL_FALLBACK_ON_QUOTA = True

    res = _generate(client, vi_notebook)

    assert res.status_code == 400
    assert 'Vietnamese' in res.json()['detail'] or 'tiếng Việt' in res.json()['detail']
    assert Flashcard.objects.count() == 0


def test_ml_primary_is_skipped_for_a_vietnamese_source(client, vi_notebook, settings, monkeypatch):
    settings.USE_ML_PRIMARY = True
    settings.USE_LOCAL_FALLBACK_ON_QUOTA = True
    provider = _CapturingProvider()
    monkeypatch.setattr('notebooks.services.generate.get_ai_provider', lambda: provider)
    calls = []
    def spy(*a, **k):
        calls.append(a)
        raise RuntimeError('extractive ran')   # the cascade would swallow this; the list is the proof
    monkeypatch.setattr('notebooks.services.generate._generate_flashcards_ml', spy)

    assert _generate(client, vi_notebook).status_code == 201
    assert calls == []          # the extractive pipeline was never consulted
    assert provider.prompts
