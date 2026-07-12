from django.db.models import Avg, Sum
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

from flashcards.models import Flashcard
from notebooks.models import Notebook, Source
from quizzes.models import Quiz, QuizAttempt
from .models import StudySession
from .serializers import StudySessionSerializer


class StudySessionViewSet(viewsets.ModelViewSet):
    serializer_class = StudySessionSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['mood_before', 'mood_after']
    ordering_fields = ['started_at', 'duration_minutes']
    ordering = ['-started_at']

    def get_queryset(self):
        return StudySession.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        user = request.user
        sessions = StudySession.objects.filter(user=user)
        attempts = QuizAttempt.objects.filter(user=user)
        completed = attempts.filter(is_completed=True)

        total_study_minutes = sessions.aggregate(total=Sum('duration_minutes'))['total'] or 0
        avg_quiz_score = completed.aggregate(avg=Avg('score'))['avg']

        flashcards = Flashcard.objects.filter(user=user)
        total_reviews = flashcards.aggregate(
            correct=Sum('correct_count'),
            incorrect=Sum('incorrect_count'),
        )
        correct = total_reviews['correct'] or 0
        incorrect = total_reviews['incorrect'] or 0
        review_total = correct + incorrect

        notebooks_count = Notebook.objects.filter(user=user).count()
        sources_count = Source.objects.filter(notebook__user=user).count()

        return Response({
            'notebooks_count': notebooks_count,
            'sources_count': sources_count,
            'flashcards_count': flashcards.count(),
            'quizzes_count': Quiz.objects.filter(user=user).count(),
            'quiz_attempts_count': attempts.count(),
            'quiz_attempts_completed': completed.count(),
            'average_quiz_score': round(avg_quiz_score, 1) if avg_quiz_score is not None else None,
            'total_study_minutes': total_study_minutes,
            'study_sessions_count': sessions.count(),
            'flashcard_reviews': review_total,
            'flashcard_accuracy': round((correct / review_total) * 100, 1) if review_total else None,
        })

    @action(detail=False, methods=['get'])
    def subjects(self, request):
        """Available subjects from the topic hierarchy for learning path filtering."""
        try:
            import pandas as pd
            from ml_pipeline.config import PROCESSED_DIR

            path = PROCESSED_DIR / 'topic_hierarchy.parquet'
            if not path.exists():
                return Response({'subjects': []})
            hierarchy = pd.read_parquet(path)
            subjects = sorted(hierarchy['subject'].unique().tolist())
            return Response({'subjects': subjects})
        except Exception as exc:
            return Response({'subjects': [], 'detail': str(exc)}, status=503)

    @action(detail=False, methods=['get'])
    def recommendations(self, request):
        """Content-based study topic recommendations from ML pipeline."""
        study_text = request.query_params.get('text', '')
        limit = min(int(request.query_params.get('limit', 5)), 20)
        try:
            from ml.adapter import get_study_recommendations
            items = get_study_recommendations(request.user, study_text=study_text, n=limit)
            return Response({'recommendations': items, 'method': 'content_based'})
        except Exception as exc:
            return Response(
                {'recommendations': [], 'method': 'unavailable', 'detail': str(exc)},
                status=503,
            )

    @action(detail=False, methods=['get'])
    def learning_path(self, request):
        """Adaptive learning path based on topic hierarchy and performance."""
        subject = request.query_params.get('subject')
        limit = min(int(request.query_params.get('limit', 15)), 50)
        try:
            from ml.adapter import get_learning_path
            path = get_learning_path(request.user, subject=subject, limit=limit)
            return Response({'learning_path': path, 'subject': subject})
        except Exception as exc:
            return Response(
                {'learning_path': [], 'detail': str(exc)},
                status=503,
            )
