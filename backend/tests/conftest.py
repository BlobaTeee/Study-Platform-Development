"""Shared fixtures for the backend API tests.

Authentication is bypassed with `force_authenticate`: Supabase issues the
real tokens, and what these tests cover starts after a token has been
accepted. The one place the token itself matters is tests/test_auth.py.
"""
import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from notebooks.models import Notebook, Source
from users.models import UserProfile

User = get_user_model()

# Enough words to pass ml_pipeline.source_guard for both flashcards and quizzes.
SOURCE_TEXT = ' '.join(
    f'Sentence number {i} explains a distinct idea about the topic under study.'
    for i in range(80)
)


@pytest.fixture(autouse=True)
def _english_unless_asked(settings):
    """The app defaults to Vietnamese; most tests check the English wording,
    so they run with English as the fallback. test_i18n checks the real
    default."""
    settings.LANGUAGE_CODE = 'en'


@pytest.fixture(autouse=True)
def _isolated_cache():
    """Throttle counters live in the (per-process) cache; never let one test's
    requests count against the next."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _forget_failed_models():
    """Which Gemini models are currently unavailable is per-process state by
    design, so one test's broken model would otherwise be skipped by the next."""
    from notebooks.services.gemini_client import forget_failures
    forget_failures()
    yield
    forget_failures()


@pytest.fixture(autouse=True)
def _no_ocr(monkeypatch):
    """No test runs Tesseract unless it asks (tests/test_ocr.py): a scanned
    PDF fails as it does where Tesseract is not installed."""
    from notebooks.services import ocr
    monkeypatch.setattr(ocr, 'available', lambda: False)


class _NoProvider:
    """Stands in for Gemini/Ollama: every call fails at once, with the error
    the code already treats as "provider unavailable"."""
    name = 'none'

    def generate_json(self, prompt):
        from notebooks.services.gemini_client import GeminiNotConfiguredError
        raise GeminiNotConfiguredError('no provider in tests')

    def summarize(self, text, title=''):
        raise RuntimeError('no provider in tests')


def _no_translation(texts, source, target):
    raise RuntimeError('no translation model in tests')


@pytest.fixture(autouse=True)
def _no_outside_generation(settings, monkeypatch):
    """No test may reach a real provider or the spaCy pipeline.

    A mock test started against an empty pool tops itself up by generating;
    a due-cards fetch may regenerate a flagged card. Left alone, either would
    call Gemini or Ollama and wait on the network for a minute. With the
    provider stubbed and the local fallback off, generation fails fast and
    the view answers with whatever it does when nothing can be generated.
    """
    settings.USE_ML_PRIMARY = False
    settings.USE_LOCAL_FALLBACK_ON_QUOTA = False
    # Synchronous in tests; one test turns the background path on itself.
    settings.MISCONCEPTIONS_IN_BACKGROUND = False
    settings.CARD_VARIANTS_IN_BACKGROUND = False
    for target in ('notebooks.services.generate.get_ai_provider',
                   'notebooks.services.ai_provider.get_ai_provider',
                   'notebooks.services.ingest.get_ai_provider',
                   'quizzes.services.concepts.get_ai_provider',
                   'quizzes.services.practice.get_ai_provider',
                   'quizzes.services.explain.get_ai_provider',
                   'flashcards.services.tutor.get_ai_provider',
                   'study_sessions.forgotten.get_ai_provider',
                   'notebooks.services.key_points.get_ai_provider',
                   'quizzes.services.misconceptions.get_ai_provider',
                   'study_sessions.feynman.get_ai_provider'):
        monkeypatch.setattr(target, lambda: _NoProvider())
    # Nor load the local translation model.
    monkeypatch.setattr('notebooks.services.translate.machine_translate', _no_translation)
    monkeypatch.setattr('notebooks.services.translate.machine_translate_in_context', _no_translation)


@pytest.fixture
def user(db):
    u = User.objects.create_user(username='supabase:test-user', email='student@example.com')
    UserProfile.objects.create(user=u, supabase_uid='11111111-1111-1111-1111-111111111111')
    return u


@pytest.fixture
def other_user(db):
    u = User.objects.create_user(username='supabase:other-user', email='other@example.com')
    UserProfile.objects.create(user=u, supabase_uid='22222222-2222-2222-2222-222222222222')
    return u


@pytest.fixture
def client(user):
    c = APIClient(HTTP_HOST='localhost')
    c.force_authenticate(user)
    return c


@pytest.fixture
def other_client(other_user):
    """The second student, for everything about sharing."""
    c = APIClient(HTTP_HOST='localhost')
    c.force_authenticate(other_user)
    return c


@pytest.fixture
def shared_notebook(notebook, other_user):
    """`notebook` with the second student added as a member."""
    from notebooks.models import NotebookMember
    NotebookMember.objects.create(notebook=notebook, user=other_user, role='member')
    return notebook


def make_source(notebook, title='Lecture', text=SOURCE_TEXT):
    return Source.objects.create(
        notebook=notebook, title=title, file=f'notebook_sources/{title}.pdf',
        file_type='pdf', extracted_text=text, status='ready',
    )


@pytest.fixture
def notebook(user):
    """A notebook with two processed sources, as generation expects."""
    nb = Notebook.objects.create(user=user, title='Biology')
    make_source(nb, 'Cells')
    make_source(nb, 'Genetics')
    return nb
