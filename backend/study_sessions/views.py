from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Sum, Count, Q
from datetime import timedelta

from .models import StudySession, StudyStreak, CardReview
from .serializers import (
    StudySessionSerializer, StudySessionCreateSerializer,
    CardReviewSerializer, StudyStreakSerializer
)
from flashcards.models import Flashcard


class StudySessionViewSet(viewsets.ModelViewSet):
    serializer_class = StudySessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return StudySession.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def get_serializer_class(self):
        if self.action == 'create':
            return StudySessionCreateSerializer
        return StudySessionSerializer

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """Start a study session."""
        session = self.get_object()
        if session.actual_start:
            return Response(
                {'error': 'Session already started'},
                status=status.HTTP_400_BAD_REQUEST
            )
        session.actual_start = timezone.now()
        session.save()
        return Response(StudySessionSerializer(session).data)

    @action(detail=True, methods=['post'])
    def end(self, request, pk=None):
        """End a study session."""
        session = self.get_object()
        if not session.actual_start:
            return Response(
                {'error': 'Session not started'},
                status=status.HTTP_400_BAD_REQUEST
            )

        session.actual_end = timezone.now()
        session.completed = True

        # Update mood and focus if provided
        if 'mood_after' in request.data:
            session.mood_after = request.data['mood_after']
        if 'focus_level' in request.data:
            session.focus_level = request.data['focus_level']

        session.save()

        # Update study streak
        self._update_streak(request.user)

        return Response(StudySessionSerializer(session).data)

    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """Get upcoming scheduled sessions."""
        now = timezone.now()
        sessions = self.get_queryset().filter(
            scheduled_start__gte=now,
            completed=False
        ).order_by('scheduled_start')[:7]
        return Response(StudySessionSerializer(sessions, many=True).data)

    @action(detail=False, methods=['get'])
    def today(self, request):
        """Get today's sessions."""
        today = timezone.now().date()
        tomorrow = today + timedelta(days=1)
        sessions = self.get_queryset().filter(
            scheduled_start__date=today
        ).order_by('scheduled_start')
        return Response(StudySessionSerializer(sessions, many=True).data)

    @action(detail=True, methods=['post'])
    def record_card_result(self, request, pk=None):
        """Record flashcard performance during session."""
        session = self.get_object()
        flashcard_id = request.data.get('flashcard_id')
        result = request.data.get('result')  # 'again', 'hard', 'good', 'easy'

        if not flashcard_id or not result:
            return Response(
                {'error': 'Missing flashcard_id or result'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            flashcard = Flashcard.objects.get(id=flashcard_id, user=request.user)
        except Flashcard.DoesNotExist:
            return Response(
                {'error': 'Flashcard not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Create or update card review
        review, created = CardReview.objects.get_or_create(
            user=request.user,
            flashcard=flashcard,
            review_date=timezone.now().date(),
            defaults={'session': session, 'result': result}
        )

        if not created:
            review.result = result
            review.session = session

        review.calculate_next_review()

        # Update session stats
        session.cards_reviewed += 1
        if result in ['good', 'easy']:
            session.cards_correct += 1
        else:
            session.cards_incorrect += 1
        session.save()

        return Response(CardReviewSerializer(review).data)

    def _update_streak(self, user):
        """Update study streak after session completion."""
        streak, created = StudyStreak.objects.get_or_create(user=user)
        today = timezone.now().date()
        
        # Add session duration to total
        completed_today = StudySession.objects.filter(
            user=user,
            completed=True,
            created_at__date=today
        )
        total_today = sum(s.actual_duration for s in completed_today if s.actual_duration)
        
        # Only count first session of the day for streak
        if not streak.last_session_date or streak.last_session_date < today:
            streak.update_streak(today)
            streak.total_study_minutes += total_today
            streak.save()


class StudyStreakViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StudyStreakSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return StudyStreak.objects.filter(user=self.request.user)

    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user's streak."""
        streak, created = StudyStreak.objects.get_or_create(user=request.user)
        return Response(StudyStreakSerializer(streak).data)


class CardReviewViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CardReviewSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return CardReview.objects.filter(user=self.request.user)

    @action(detail=False, methods=['get'])
    def due_today(self, request):
        """Get cards due for review today."""
        today = timezone.now().date()
        reviews = self.get_queryset().filter(
            Q(next_review_date__lte=today) | Q(next_review_date__isnull=True)
        ).select_related('flashcard')[:20]
        return Response(CardReviewSerializer(reviews, many=True).data)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get review statistics."""
        user = request.user
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)

        total_reviews = CardReview.objects.filter(user=user).count()
        reviews_this_week = CardReview.objects.filter(
            user=user,
            review_date__date__gte=week_ago
        ).count()
        accuracy_this_week = CardReview.objects.filter(
            user=user,
            review_date__date__gte=week_ago,
            result__in=['good', 'easy']
        ).count()

        accuracy_pct = (accuracy_this_week / reviews_this_week * 100) if reviews_this_week > 0 else 0

        return Response({
            'total_reviews': total_reviews,
            'reviews_this_week': reviews_this_week,
            'accuracy_this_week_percent': round(accuracy_pct, 1),
        })
