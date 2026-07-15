from django.db.models import Avg, Sum
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from flashcards.models import Flashcard
from notebooks.models import Notebook, Source
from quizzes.models import Quiz, QuizAttempt
from . import insights

WEAK_CARDS_LIMIT = 20


class AnalyticsViewSet(viewsets.ViewSet):
    """Read-only study insights computed from the user's own activity.

    Everything here derives from what the user actually did: their cards, their
    review history, their documents. The previous taxonomy-backed recommender
    and learning path were removed — they could only suggest topics from a fixed
    5-subject STEM list, which does not match real uploaded documents.
    """
    permission_classes = [permissions.IsAuthenticated]

    @action(detail=False, methods=['get'])
    def summary(self, request):
        user = request.user
        completed = QuizAttempt.objects.filter(user=user, is_completed=True)
        avg_quiz_score = completed.aggregate(avg=Avg('score'))['avg']

        flashcards = Flashcard.objects.filter(user=user)
        totals = flashcards.aggregate(correct=Sum('correct_count'),
                                      incorrect=Sum('incorrect_count'))
        correct = totals['correct'] or 0
        incorrect = totals['incorrect'] or 0
        reviews = correct + incorrect

        return Response({
            'notebooks_count': Notebook.objects.filter(user=user).count(),
            'sources_count': Source.objects.filter(notebook__user=user).count(),
            'flashcards_count': flashcards.count(),
            'quizzes_count': Quiz.objects.filter(user=user).count(),
            'quiz_attempts_completed': completed.count(),
            'average_quiz_score': round(avg_quiz_score, 1) if avg_quiz_score is not None else None,
            'flashcard_reviews': reviews,
            'flashcard_correct': correct,
            'flashcard_incorrect': incorrect,
            'flashcard_accuracy': round(correct / reviews * 100, 1) if reviews else None,
        })

    @action(detail=False, methods=['get'])
    def recommendations(self, request):
        """What to review next, and which documents you're weakest on."""
        user = request.user
        limit = min(int(request.query_params.get('limit', 5)), WEAK_CARDS_LIMIT)

        cards = list(
            Flashcard.objects.filter(user=user)
            .values('id', 'question', 'correct_count', 'incorrect_count', 'tags')
        )
        titles = dict(
            Source.objects.filter(notebook__user=user).values_list('id', 'title')
        )

        return Response({
            'weak_cards': insights.rank_weak_cards(cards, limit=limit),
            'weak_sources': insights.per_source_accuracy(cards, titles),
        })
