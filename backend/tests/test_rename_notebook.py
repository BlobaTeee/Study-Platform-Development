"""A notebook named in haste can be renamed, not only deleted."""
import pytest

from notebooks.models import Notebook

pytestmark = pytest.mark.django_db


def test_the_owner_renames_a_notebook(client, notebook):
    res = client.patch(f'/api/notebooks/notebooks/{notebook.id}/', {'title': 'Sinh học 12'}, format='json')
    assert res.status_code == 200 and res.json()['title'] == 'Sinh học 12'
    notebook.refresh_from_db()
    assert notebook.title == 'Sinh học 12'


def test_a_blank_title_is_refused(client, notebook):
    res = client.patch(f'/api/notebooks/notebooks/{notebook.id}/', {'title': '   '}, format='json')
    assert res.status_code == 400 and 'title' in res.json()


def test_someone_elses_notebook_is_not_found(client, other_user):
    theirs = Notebook.objects.create(user=other_user, title='Theirs')
    res = client.patch(f'/api/notebooks/notebooks/{theirs.id}/', {'title': 'Mine'}, format='json')
    assert res.status_code == 404
    theirs.refresh_from_db()
    assert theirs.title == 'Theirs'
