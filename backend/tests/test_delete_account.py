"""Deleting your account removes everything — here and at Supabase."""
import pytest
from django.contrib.auth import get_user_model

from flashcards.models import Flashcard
from notebooks.models import Notebook
from users.models import UserProfile

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def admin_calls(monkeypatch, settings):
    settings.SUPABASE_SERVICE_ROLE_KEY = 'service-key'
    calls = []
    monkeypatch.setattr('users.services.supabase_admin.delete_auth_user',
                        lambda uid: calls.append(uid) or True)
    return calls


def test_deleting_the_account_removes_the_user_and_their_data(client, user, notebook, admin_calls):
    Flashcard.objects.create(user=user, question='q', answer='a')
    uid = user.profile.supabase_uid

    res = client.delete('/api/users/profiles/me/')

    assert res.status_code == 204
    assert not User.objects.filter(id=user.id).exists()
    assert not Notebook.objects.filter(id=notebook.id).exists()
    assert Flashcard.objects.count() == 0
    assert admin_calls == [uid]


def test_the_supabase_user_goes_first_so_a_failure_there_deletes_nothing(client, user, monkeypatch, settings):
    settings.SUPABASE_SERVICE_ROLE_KEY = 'service-key'
    monkeypatch.setattr('users.services.supabase_admin.delete_auth_user', lambda uid: False)

    res = client.delete('/api/users/profiles/me/')

    assert res.status_code == 503
    assert User.objects.filter(id=user.id).exists()


def test_without_a_service_key_the_local_data_still_goes(client, user, settings, caplog):
    # Dev boxes have no service-role key; the auth row is left for the
    # operator and logged, rather than trapping the student in an account
    # they asked to delete.
    settings.SUPABASE_SERVICE_ROLE_KEY = ''

    res = client.delete('/api/users/profiles/me/')

    assert res.status_code == 204
    assert not User.objects.filter(id=user.id).exists()
    assert 'SUPABASE_SERVICE_ROLE_KEY' in caplog.text


def test_other_users_are_untouched(client, user, other_user, admin_calls):
    client.delete('/api/users/profiles/me/')
    assert User.objects.filter(id=other_user.id).exists()
