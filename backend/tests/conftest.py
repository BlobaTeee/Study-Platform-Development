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
def _isolated_cache():
    """Throttle counters live in the (per-process) cache; never let one test's
    requests count against the next."""
    cache.clear()
    yield
    cache.clear()


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
