"""The browser tells the API its zone once; the API refuses zones it can't
resolve, because a bad one would silently mis-time every reminder."""
import pytest

pytestmark = pytest.mark.django_db

URL = '/api/users/profiles/update_profile/'


def test_a_valid_timezone_is_stored(client, user):
    res = client.put(URL, {'timezone': 'Europe/London'}, format='json')

    assert res.status_code == 200
    assert res.json()['timezone'] == 'Europe/London'
    user.profile.refresh_from_db()
    assert user.profile.timezone == 'Europe/London'


def test_an_unknown_timezone_is_refused(client, user):
    res = client.put(URL, {'timezone': 'Mars/Olympus_Mons'}, format='json')

    assert res.status_code == 400
    assert 'timezone' in res.json()
    user.profile.refresh_from_db()
    assert user.profile.timezone == 'Asia/Ho_Chi_Minh'


def test_the_default_is_the_servers_zone(client):
    assert client.get('/api/users/profiles/me/').json()['timezone'] == 'Asia/Ho_Chi_Minh'
