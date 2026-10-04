"""How each member of a shared notebook is doing in it.

Scoped to the notebook on purpose: studying together is a reason to see
each other's progress here, not a licence to see anyone's whole account.
"""
from django.db.models import Count, Q

from flashcards.models import Flashcard
from notebooks.models import NotebookMember
from quizzes.models import Answer
from study_sessions.models import CardReview


def member_records(notebook, viewer) -> list[dict]:
    """One row per member: who they are, their role, and their record here."""
    members = list(NotebookMember.objects.filter(notebook=notebook).select_related('user'))
    user_ids = [m.user_id for m in members]
    cards = Flashcard.objects.filter(notebook=notebook, archived=False)

    reviews = dict(
        CardReview.objects.filter(user_id__in=user_ids, flashcard__in=cards).grades()
        .values('user_id').annotate(n=Count('id')).values_list('user_id', 'n')
    )
    # Quiz answers on this notebook's material: the firmer evidence of the two.
    answered = (Answer.objects
                .filter(quiz_attempt__user_id__in=user_ids,
                        question__quiz__sources__notebook=notebook)
                .values('quiz_attempt__user_id')
                .annotate(n=Count('id', distinct=True),
                          right=Count('id', filter=Q(is_correct=True), distinct=True)))
    accuracy = {row['quiz_attempt__user_id']: round(row['right'] / row['n'] * 100, 1)
                for row in answered if row['n']}

    return [
        {
            'user_id': m.user_id,
            'name': m.user.first_name or (m.user.email or '').split('@')[0] or 'Student',
            'email': m.user.email,
            'role': m.role,
            'is_you': m.user_id == viewer.id,
            'reviews': reviews.get(m.user_id, 0),
            'accuracy': accuracy.get(m.user_id),
        }
        for m in members
    ]
