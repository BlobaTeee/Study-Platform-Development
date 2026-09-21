from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils.translation import gettext as _
from studyplatform.throttling import GenerationRateThrottle
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from .models import Flashcard
from .serializers import FlashcardSerializer


class FlashcardViewSet(viewsets.ModelViewSet):
    serializer_class = FlashcardSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['difficulty', 'topic', 'is_public']
    search_fields = ['question', 'answer']
    ordering_fields = ['created_at', 'difficulty', 'views_count', 'correct_count']
    ordering = ['-created_at']

    def get_queryset(self):
        # Archived originals are replaced-but-not-deleted history, not live
        # cards; exclude them on both sides of the union or a public archived
        # card would still surface here even though due_today never offers it.
        mine = Flashcard.objects.filter(user=self.request.user, archived=False)
        # Anyone may read a public card; only its owner may change or delete
        # it. Narrowing the queryset (rather than checking in perform_update)
        # makes someone else's card a 404 on write, exactly like a missing one.
        if self.request.method not in permissions.SAFE_METHODS:
            return mine
        return mine | Flashcard.objects.filter(is_public=True, archived=False)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def get_throttles(self):
        # Asking the tutor is an LLM call; it shares generation's budget.
        if self.action == 'ask':
            return [GenerationRateThrottle()]
        return super().get_throttles()

    @action(detail=True, methods=['post'])
    def ask(self, request, pk=None):
        """A question about this card, after its answer has been seen."""
        from .services.tutor import MAX_QUESTION_CHARS, MAX_TURNS, TutorUnavailable, ask

        card = self.get_object()  # the write queryset: own cards only
        question = (str(request.data.get('question') or '')).strip()[:MAX_QUESTION_CHARS]
        if not question:
            return Response({'detail': _('Ask something first.')}, status=400)
        history = request.data.get('history') or []
        if not isinstance(history, list) or not all(isinstance(t, dict) for t in history):
            return Response({'detail': _('history must be a list of turns.')}, status=400)
        asked = sum(1 for t in history if t.get('role') == 'user')
        if asked >= MAX_TURNS:
            return Response({'detail': _('That is the third question on this card — try recalling it again, '
                                         'then come back if it is still unclear.')}, status=400)
        try:
            return Response({'answer': ask(card, question, history[-2 * MAX_TURNS:])})
        except TutorUnavailable as exc:
            return Response({'detail': str(exc)}, status=503)
