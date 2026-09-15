from rest_framework import viewsets, permissions
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
        return (Flashcard.objects.filter(user=self.request.user, archived=False)
                | Flashcard.objects.filter(is_public=True, archived=False))

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
