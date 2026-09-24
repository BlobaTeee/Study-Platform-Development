"""Who may do what with a shared notebook.

One place for the rule, so views do not each invent their own. Reading is
for every member; managing the notebook itself (rename, delete, invite,
remove) is the owner's; editing one generated item is for whoever made it,
or the owner of the notebook it belongs to.
"""
from __future__ import annotations

from django.db.models import Q, QuerySet

from notebooks.models import Notebook, NotebookMember

OWNER = 'owner'
MEMBER = 'member'


def notebooks_for(user) -> QuerySet:
    """Every notebook this person can open: their own, plus shared ones."""
    return Notebook.objects.filter(Q(user=user) | Q(members__user=user)).distinct()


def role_of(notebook, user) -> str | None:
    """'owner', 'member', or None for someone with no business here."""
    if notebook.user_id == user.id:
        return OWNER
    row = NotebookMember.objects.filter(notebook=notebook, user=user).first()
    return row.role if row else None


def is_member(notebook, user) -> bool:
    return role_of(notebook, user) is not None


def can_manage(notebook, user) -> bool:
    """Rename, delete, invite, remove members: the owner only."""
    return role_of(notebook, user) == OWNER


def members_of(notebook) -> list[NotebookMember]:
    return list(NotebookMember.objects.filter(notebook=notebook).select_related('user'))


def can_edit_item(item, user) -> bool:
    """A generated card or question: its author, or the notebook's owner.

    Anyone in the notebook may study shared material; changing it is not
    everyone's to do, or one member's correction quietly rewrites another
    member's deck.
    """
    if _author_id(item) == user.id:
        return True
    notebook = _notebook_of(item)
    return bool(notebook) and can_manage(notebook, user)


def _author_id(item):
    """Who made it. A card carries its own user; a question belongs to the
    quiz that was generated, so its author is that quiz's owner."""
    own = getattr(item, 'user_id', None)
    if own is not None:
        return own
    quiz = getattr(item, 'quiz', None)
    return getattr(quiz, 'user_id', None)


def _notebook_of(item):
    """The notebook a card or question belongs to, via its own FK or its
    sources. Returns None when the item is not tied to one."""
    notebook = getattr(item, 'notebook', None)
    if notebook is not None:
        return notebook
    sources = getattr(item, 'sources', None)
    if sources is None:
        quiz = getattr(item, 'quiz', None)
        sources = getattr(quiz, 'sources', None) if quiz else None
    if sources is None:
        return None
    src = sources.select_related('notebook').first()
    return src.notebook if src else None
