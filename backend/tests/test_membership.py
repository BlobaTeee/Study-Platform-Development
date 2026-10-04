"""Who may see and change a notebook once it is shared."""
import pytest

from notebooks.models import Notebook, NotebookMember
from notebooks.services.membership import (
    can_edit_item, can_manage, members_of, notebooks_for, role_of,
)

pytestmark = pytest.mark.django_db


def test_creating_a_notebook_makes_its_creator_the_owner(client, user):
    res = client.post('/api/notebooks/notebooks/', {'title': 'Sinh học'}, format='json')
    nb = Notebook.objects.get(id=res.json()['id'])
    assert role_of(nb, user) == 'owner'
    assert [m.user for m in members_of(nb)] == [user]


def test_a_member_sees_the_notebook_in_their_list(client, user, other_user, notebook):
    assert notebook not in notebooks_for(other_user)
    NotebookMember.objects.create(notebook=notebook, user=other_user, role='member')
    assert notebook in notebooks_for(other_user)
    assert notebook in notebooks_for(user)          # the owner still sees it


def test_only_the_owner_manages_the_notebook(client, user, other_user, notebook):
    NotebookMember.objects.create(notebook=notebook, user=other_user, role='member')
    assert can_manage(notebook, user) is True
    assert can_manage(notebook, other_user) is False


def test_an_item_can_be_edited_by_whoever_made_it_or_by_the_owner(user, other_user, notebook):
    from flashcards.models import Flashcard
    card = Flashcard.objects.create(user=other_user, notebook=notebook, question='q', answer='a')
    NotebookMember.objects.create(notebook=notebook, user=other_user, role='member')

    assert can_edit_item(card, other_user) is True      # its author
    assert can_edit_item(card, user) is True            # the notebook's owner
    from django.contrib.auth import get_user_model
    stranger = get_user_model().objects.create_user(username='stranger')
    assert can_edit_item(card, stranger) is False


def test_role_of_a_stranger_is_none(notebook, other_user):
    assert role_of(notebook, other_user) is None
