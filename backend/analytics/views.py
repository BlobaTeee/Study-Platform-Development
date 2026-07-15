from django.db.models import Avg, F
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from flashcards.models import Flashcard
from notebooks.models import Notebook, Source
from quizzes.models import Answer, Question, Quiz, QuizAttempt
from study_sessions.models import CardReview
from . import insights

WEAK_CARDS_LIMIT = 20


def _review_tallies(user):
    """Per-card correct/incorrect counts from the user's own review record.

    Flashcard.correct_count and .incorrect_count look like the obvious source
    but nothing writes to them; CardReview rows are what self-grading produces.
    """
    return insights.tally_reviews(
        list(CardReview.objects.filter(user=user).values('flashcard_id', 'result'))
    )


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
        reviews_qs = CardReview.objects.filter(user=user)
        correct = reviews_qs.filter(result__in=insights.CORRECT_RESULTS).count()
        incorrect = reviews_qs.filter(result__in=insights.INCORRECT_RESULTS).count()
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

        cards = insights.attach_review_counts(
            list(Flashcard.objects.filter(user=user).values('id', 'question', 'tags')),
            _review_tallies(user),
        )
        titles = dict(
            Source.objects.filter(notebook__user=user).values_list('id', 'title')
        )

        # Per-document mastery draws on every mode that grades an item against a
        # source. Flashcards alone would ignore the quiz answers on record, which
        # are the firmer evidence of the two — they are marked, not self-reported.
        events = insights.flashcard_events(cards) + insights.quiz_events(
            list(Question.objects.filter(quiz__user=user)
                 .values('id', quiz_description=F('quiz__description'))),
            list(Answer.objects.filter(quiz_attempt__user=user)
                 .values('question_id', 'is_correct')),
        )

        return Response({
            'weak_cards': insights.rank_weak_cards(cards, limit=limit),
            'weak_sources': insights.per_source_mastery(events, titles),
        })
