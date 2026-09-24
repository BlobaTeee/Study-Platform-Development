from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from datetime import timedelta

from . import scheduling
from .models import StudySession, StudyStreak, CardReview
from .serializers import (
    StudySessionSerializer, StudySessionCreateSerializer,
    CardReviewSerializer, StudyStreakSerializer
)
from flashcards.models import Flashcard
from notebooks.services.membership import notebooks_for
from flashcards.services.regeneration import (
    MAX_REGENERATIONS_PER_FETCH, merge_replacements, select_for_regeneration,
)

DUE_CARDS_DEFAULT = 50
DUE_CARDS_LIMIT = 200


def studiable_cards(user):
    """Every live card this person may study: their own, and the ones in
    notebooks shared with them. One definition, so the due queue, the
    schedule and a review all agree on what is theirs to answer."""
    from django.db.models import Q
    return Flashcard.objects.filter(
        Q(user=user) | Q(notebook__in=notebooks_for(user)), archived=False
    ).distinct()


def resolve_review_request(request):
    """Validate a {flashcard_id, result} body.

    Returns ``(flashcard, result, None)``, or ``(None, None, error_response)``.
    """
    flashcard_id = request.data.get('flashcard_id')
    result = request.data.get('result')

    if result not in scheduling.RESULT_VALUES:
        return None, None, Response(
            {'error': f"result must be one of {list(scheduling.RESULT_VALUES)}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        flashcard = studiable_cards(request.user).get(id=flashcard_id)
    except (Flashcard.DoesNotExist, ValueError, TypeError):
        # A card belonging to someone else is reported the same way as a missing
        # one, so this cannot be used to probe for other users' card ids.
        return None, None, Response(
            {'error': 'Flashcard not found'},
            status=status.HTTP_404_NOT_FOUND
        )

    return flashcard, result, None


def _swap_in_variants(user, ranked, pending):
    """Replace each flagged card in `ranked` with a freshly generated one.

    A failure here must never cost the learner their study session, so a card
    that cannot be regenerated is simply returned unchanged and retried on the
    next fetch. That guarantee only holds if the try/except spans every risky
    call for a given card (the database lookups and the three-write swap, not
    just the model call), so one bad card can't 500 the whole fetch.
    """
    import time

    from notebooks.services.ai_provider import get_ai_provider
    from flashcards.services.variant_generator import generate_variant
    from flashcards.services.regeneration import (
        REGENERATION_TIME_BUDGET_SECONDS, record_failed_attempt, replace_card,
    )

    try:
        provider = get_ai_provider()
    except Exception:
        # No provider this fetch means no regeneration this fetch, not a
        # broken study page: flagged cards stay flagged and are retried next
        # time the learner fetches their due cards.
        return ranked

    replacements = {}
    deadline = time.monotonic() + REGENERATION_TIME_BUDGET_SECONDS
    for entry in pending:
        # A provider that times out on each attempt would otherwise hold the
        # study page for minutes. Whatever is left keeps its flag and is picked
        # up next fetch, which is the degradation this flow is built around.
        if time.monotonic() >= deadline:
            break
        try:
            card = Flashcard.objects.filter(id=entry['id'], user=user).first()
            if card is None:
                continue
            excerpt = _source_excerpt(user, entry.get('source_ids', []))
            variant = generate_variant(card.question, card.answer,
                                       provider=provider, excerpt=excerpt)
            if not variant:
                # Nothing usable came back. Count it, so a card that can never
                # be regenerated stops consuming a slot on every future fetch.
                record_failed_attempt(card)
                continue
            new_card = replace_card(card, variant)
        except Exception:
            continue
        replacements[entry['id']] = {
            'id': new_card.id, 'question': new_card.question,
            'answer': new_card.answer, 'difficulty': new_card.difficulty,
            'source_ids': list(new_card.sources.values_list('id', flat=True)),
            'status': entry['status'],
            'overdue_days': entry['overdue_days'], 'regenerated': True,
        }

    return merge_replacements(ranked, replacements)


def _source_excerpt(user, source_ids, limit=4000):
    """The text the card was generated from, so a variant stays on topic."""
    from notebooks.models import Source

    if not source_ids:
        return ""
    texts = Source.objects.filter(
        id__in=source_ids, notebook__user=user
    ).values_list('extracted_text', flat=True)
    return "\n\n".join(t for t in texts if t)[:limit]


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
        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        sessions = self.get_queryset().filter(
            scheduled_start__date=today
        ).order_by('scheduled_start')
        return Response(StudySessionSerializer(sessions, many=True).data)

    @action(detail=True, methods=['post'])
    def record_card_result(self, request, pk=None):
        """Record flashcard performance during a scheduled session."""
        session = self.get_object()
        flashcard, result, error = resolve_review_request(request)
        if error:
            return error

        review = CardReview.record(request.user, flashcard, result, session=session)

        session.cards_reviewed += 1
        if result in scheduling.CORRECT_RESULTS:
            session.cards_correct += 1
        else:
            session.cards_incorrect += 1
        session.save()

        return Response(CardReviewSerializer(review).data)

    def _update_streak(self, user):
        """Update study streak after session completion."""
        streak, created = StudyStreak.objects.get_or_create(user=user)
        today = timezone.localdate()
        
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

    @action(detail=False, methods=['post'])
    def record(self, request):
        """Record a self-graded flashcard review.

        Unlike record_card_result on StudySession, this needs no session: the
        flashcards page lets you grade cards without scheduling one first, and
        CardReview.session is nullable to allow exactly that.
        """
        flashcard, result, error = resolve_review_request(request)
        if error:
            return error

        review = CardReview.record(request.user, flashcard, result)
        return Response(CardReviewSerializer(review).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def due_today(self, request):
        """The flashcards ready to study: scheduled for today or earlier, plus
        cards never reviewed.

        This returns cards rather than reviews. Reading review rows could not
        answer the question: a card has one row per review, so a card would
        appear once per time it was studied, and a card never reviewed has no
        row at all and so could never be offered.
        """
        user = request.user
        limit = min(int(request.query_params.get('limit', DUE_CARDS_DEFAULT)),
                    DUE_CARDS_LIMIT)
        schedule = scheduling.latest_schedule(
            list(CardReview.objects.filter(user=user).latest_per_card()
                 .values('flashcard_id', 'next_review_date', 'review_date'))
        )
        cards = list(studiable_cards(user)
                     .values('id', 'question', 'answer', 'difficulty',
                             'needs_regeneration', 'regeneration_attempts'))
        # Sources ride along so the study page can scope the due queue to a
        # document (`?due=1&source=…`). One query for the collection.
        by_card: dict[int, list[int]] = {}
        for card_id, source_id in (Flashcard.sources.through.objects
                                   .filter(flashcard__in=studiable_cards(user))
                                   .values_list('flashcard_id', 'source_id')):
            by_card.setdefault(card_id, []).append(source_id)
        for card in cards:
            card['source_ids'] = by_card.get(card['id'], [])
        ranked = scheduling.rank_due_cards(cards, schedule, timezone.localdate(),
                                           limit=limit)

        pending = select_for_regeneration(ranked, MAX_REGENERATIONS_PER_FETCH)
        if pending:
            ranked = _swap_in_variants(user, ranked, pending)

        # needs_regeneration is selection-policy plumbing, not part of the
        # public shape: replacements never carry it, so leaving it on
        # originals would make the two kinds of entry disagree for no reason.
        for entry in ranked:
            entry.pop('needs_regeneration', None)
            entry.pop('regeneration_attempts', None)

        return Response(ranked)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get review statistics."""
        user = request.user
        today = timezone.localdate()
        week_ago = today - timedelta(days=7)

        total_reviews = CardReview.objects.grades().filter(user=user).count()
        reviews_this_week = CardReview.objects.grades().filter(
            user=user,
            review_date__date__gte=week_ago
        ).count()
        accuracy_this_week = CardReview.objects.grades().filter(
            user=user,
            review_date__date__gte=week_ago,
            result__in=['good', 'easy']
        ).count()

        # None, not 0, when nothing was reviewed: "0% recalled" reads as failure
        # rather than "not studied yet". Matches analytics summary's accuracy, and
        # lets the frontend's null-guard omit the clause entirely.
        accuracy_pct = (round(accuracy_this_week / reviews_this_week * 100, 1)
                        if reviews_this_week > 0 else None)

        return Response({
            'total_reviews': total_reviews,
            'reviews_this_week': reviews_this_week,
            'accuracy_this_week_percent': accuracy_pct,
        })
