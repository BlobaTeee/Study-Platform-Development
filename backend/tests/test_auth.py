"""The Supabase token is the front door: a valid one provisions a Django user
on first sight and keeps its email in step afterwards."""
import types

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from users import authentication
from users.models import UserProfile

pytestmark = pytest.mark.django_db

User = get_user_model()
UID = '33333333-3333-3333-3333-333333333333'
URL = '/api/users/profiles/me/'


@pytest.fixture
def accept_token(monkeypatch):
    """Make any bearer token decode to the payload given, without JWKS."""
    def _accept(payload):
        fake_key = types.SimpleNamespace(key='unused')
        monkeypatch.setattr(authentication, '_get_jwk_client',
                            lambda: types.SimpleNamespace(
                                get_signing_key_from_jwt=lambda token: fake_key))
        monkeypatch.setattr(authentication.jwt, 'decode',
                            lambda token, key, algorithms, audience: payload)
    return _accept


def _client_with_token():
    return APIClient(HTTP_HOST='localhost', HTTP_AUTHORIZATION='Bearer any-token')


def test_first_request_provisions_a_user_and_profile(accept_token):
    accept_token({'sub': UID, 'email': 'new@example.com',
                  'user_metadata': {'username': 'newbie'}})

    res = _client_with_token().get(URL)

    assert res.status_code == 200
    user = User.objects.get(profile__supabase_uid=UID)
    assert user.username == f'supabase:{UID}'
    assert user.email == 'new@example.com'
    assert user.first_name == 'newbie'
    assert res.json()['email'] == 'new@example.com'


def test_a_google_or_github_sign_in_is_named_from_the_providers_metadata(accept_token):
    # OAuth sign-ups carry no `username`; Google sets full_name, GitHub
    # user_name. Neither should fall through to the raw email prefix.
    accept_token({'sub': UID, 'email': 'lan.nguyen@gmail.com',
                  'user_metadata': {'full_name': 'Lan Nguyễn', 'name': 'Lan Nguyễn',
                                    'avatar_url': 'https://x/y.png'}})

    assert _client_with_token().get(URL).status_code == 200
    assert User.objects.get(profile__supabase_uid=UID).first_name == 'Lan Nguyễn'


def test_later_requests_reuse_the_same_user(accept_token):
    accept_token({'sub': UID, 'email': 'new@example.com'})
    _client_with_token().get(URL)

    _client_with_token().get(URL)

    assert User.objects.filter(profile__supabase_uid=UID).count() == 1
    assert UserProfile.objects.filter(supabase_uid=UID).count() == 1


def test_an_email_changed_at_supabase_is_synced_on_the_next_request(accept_token):
    accept_token({'sub': UID, 'email': 'old@example.com'})
    _client_with_token().get(URL)
    accept_token({'sub': UID, 'email': 'renamed@example.com'})

    _client_with_token().get(URL)

    assert User.objects.get(profile__supabase_uid=UID).email == 'renamed@example.com'


def test_a_display_name_changed_at_supabase_is_synced_on_the_next_request(accept_token):
    accept_token({'sub': UID, 'email': 'a@example.com', 'user_metadata': {'username': 'old'}})
    _client_with_token().get(URL)
    accept_token({'sub': UID, 'email': 'a@example.com', 'user_metadata': {'username': 'new name'}})
    _client_with_token().get(URL)
    assert User.objects.get(profile__supabase_uid=UID).first_name == 'new name'


def test_a_token_without_a_subject_is_refused(accept_token):
    accept_token({'email': 'nobody@example.com'})

    res = _client_with_token().get(URL)

    assert res.status_code == 401
    assert User.objects.count() == 0


def test_no_bearer_header_means_anonymous_and_refused():
    res = APIClient(HTTP_HOST='localhost').get(URL)

    assert res.status_code == 401
    assert res['WWW-Authenticate'] == 'Bearer'
