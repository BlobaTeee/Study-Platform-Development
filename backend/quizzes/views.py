from django.db.models import Q
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from .models import (
    Quiz, Question, QuizAttempt, Answer, MockTest, MockTestQuestion, PlannedTest,
)
from .serializers import (
    QuizSerializer, QuestionSerializer, QuizAttemptSerializer, AnswerSerializer,
    MockTestSerializer, MockTestQuestionReviewSerializer, PlannedTestSerializer,
)
from .services.paper import (
    sample_paper, source_accuracy, source_weights, clamp_int,
    MIN_QUESTIONS, MAX_QUESTIONS, MIN_DURATION_MINUTES, MAX_DURATION_MINUTES,
)


class QuizViewSet(viewsets.ModelViewSet):
    serializer_class = QuizSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['topic', 'is_public', 'is_published']
    search_fields = ['title', 'description']
    ordering_fields = ['created_at', 'title']
    ordering = ['-created_at']

    def get_queryset(self):
        return Quiz.objects.filter(user=self.request.user) | Quiz.objects.filter(is_public=True)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def start_attempt(self, request, pk=None):
        quiz = self.get_object()
        attempt = QuizAttempt.objects.create(quiz=quiz, user=request.user)
        serializer = QuizAttemptSerializer(attempt)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class QuestionViewSet(viewsets.ModelViewSet):
    serializer_class = QuestionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Question.objects.filter(quiz__user=self.request.user)

    def perform_create(self, serializer):
        quiz = Quiz.objects.get(pk=self.request.data.get('quiz'))
        if quiz.user != self.request.user:
            return Response({'detail': 'Not allowed'}, status=status.HTTP_403_FORBIDDEN)
        serializer.save()


class QuizAttemptViewSet(viewsets.ModelViewSet):
    serializer_class = QuizAttemptSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return QuizAttempt.objects.filter(user=self.request.user)

    @action(detail=True, methods=['post'])
    def submit_answer(self, request, pk=None):
        attempt = self.get_object()
        question_id = request.data.get('question_id')
        user_answer = request.data.get('answer')

        question = Question.objects.get(pk=question_id)
        is_correct = user_answer == question.correct_answer

        answer = Answer.objects.create(
            quiz_attempt=attempt,
            question=question,
            user_answer=user_answer,
            is_correct=is_correct,
            points_earned=1 if is_correct else 0
        )

        serializer = AnswerSerializer(answer)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        attempt = self.get_object()
        attempt.is_completed = True
        attempt.completed_at = request.data.get('completed_at')
        
        total_correct = attempt.answers.filter(is_correct=True).count()
        total_questions = attempt.answers.count()
        attempt.score = (total_correct / total_questions * 100) if total_questions > 0 else 0
        attempt.total_points = total_questions

        attempt.save()
        serializer = QuizAttemptSerializer(attempt)
        return Response(serializer.data)


def _source_filter(field_prefix, source_ids):
    """OR of `description__contains` across a notebook's source ids.

    This is a prefilter, not the real check: `source:3` is also a substring of
    `source:30`, so it may match a quiz that mentions a different source
    entirely. That is fine, and deliberate — a prefilter is only required
    never to return too little, and the exact check (`parse_source_ids`
    followed by `if sid in source_ids`) still runs on every row this yields.
    Do not remove that exact check on the theory that this filter is precise
    enough on its own; it isn't.
    """
    field = f'{field_prefix}description__contains'
    # An empty Q() matches everything, which would silently widen the scan to
    # every quiz the user owns rather than narrowing it, so an empty list of
    # source ids must produce a filter that matches nothing instead.
    if not source_ids:
        return Q(pk__in=[])
    query = Q()
    for sid in source_ids:
        query |= Q(**{field: f'source:{sid}'})
    return query


def _question_pool(user, source_ids):
    """Every question generated from this notebook's documents.

    Source ids are parsed out of the quiz description rather than matched as a
    substring: `source:3` is a prefix of `source:30`, so substring matching
    would quietly mix in another document's questions.
    """
    from analytics import insights

    if not source_ids:
        return []

    # Narrowed at the database layer to quizzes that could mention one of
    # this notebook's sources, rather than scanning the user's entire quiz
    # history on every "start a test" press — see _source_filter for why
    # over-matching here is safe.
    pool = []
    for row in (Question.objects.filter(quiz__user=user)
                .filter(_source_filter('quiz__', source_ids))
                .values('id', 'quiz__description')):
        matched = [sid for sid in insights.parse_source_ids(row['quiz__description'])
                   if sid in source_ids]
        if matched:
            pool.append({'id': row['id'], 'source_ids': matched})
    return pool


def _source_accuracy(user, source_ids):
    """How well the user has answered questions from this notebook's own
    documents so far — the weighting has no use for accuracy on unrelated
    material, so this is scoped rather than pulling the user's whole history.
    """
    from analytics import insights

    if not source_ids:
        return {}

    rows = [
        {'source_ids': [sid for sid in insights.parse_source_ids(row['question__quiz__description'])
                        if sid in source_ids],
         'is_correct': row['is_correct']}
        for row in Answer.objects.filter(quiz_attempt__user=user)
        .filter(_source_filter('question__quiz__', source_ids))
        .values('question__quiz__description', 'is_correct')
    ]
    return source_accuracy(rows)


class MockTestViewSet(viewsets.ModelViewSet):
    """Sit a timed paper drawn from a whole notebook."""
    serializer_class = MockTestSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        return (MockTest.objects.filter(user=self.request.user)
                .select_related('notebook')
                .prefetch_related('paper__question'))

    def create(self, request, *args, **kwargs):
        from notebooks.models import Notebook

        notebook = Notebook.objects.filter(
            id=request.data.get('notebook'), user=request.user).first()
        if notebook is None:
            return Response({'detail': 'Notebook not found.'}, status=404)

        # Parse defensively rather than bare int(): a non-numeric value would
        # otherwise raise an unhandled ValueError (500) instead of a 400, and
        # an unclamped count/duration could produce a zero-question paper or
        # an already-expired deadline. See clamp_int's docstring.
        try:
            requested = clamp_int(request.data.get('question_count'),
                                   MIN_QUESTIONS, MAX_QUESTIONS, default=20)
        except ValueError as exc:
            return Response({'detail': f'question_count: {exc}'}, status=400)
        try:
            duration = clamp_int(request.data.get('duration_minutes'),
                                  MIN_DURATION_MINUTES, MAX_DURATION_MINUTES, default=30)
        except ValueError as exc:
            return Response({'detail': f'duration_minutes: {exc}'}, status=400)

        source_ids = set(notebook.sources.values_list('id', flat=True))
        pool = _question_pool(request.user, source_ids)
        if not pool:
            return Response(
                {'detail': 'No quiz questions for this notebook yet. '
                           'Generate a quiz from its documents first.'},
                status=400,
            )

        weights = source_weights(_source_accuracy(request.user, source_ids))
        chosen = sample_paper(pool, weights, count=requested)

        test = MockTest.objects.create(
            user=request.user, notebook=notebook,
            question_count=len(chosen), duration_minutes=duration,
        )
        MockTestQuestion.objects.bulk_create([
            MockTestQuestion(mock_test=test, question_id=entry['id'], order=i)
            for i, entry in enumerate(chosen)
        ])

        # Re-fetch through get_queryset() rather than refresh_from_db(): that
        # carries the same select_related/prefetch_related get_queryset()
        # already uses for reads, so the serializer walks the frozen paper's
        # questions in one query instead of one per row.
        test = self.get_queryset().get(pk=test.pk)
        data = MockTestSerializer(test).data
        # Say so rather than silently handing over a shorter paper: the student
        # is about to judge their readiness on it.
        if len(chosen) < requested:
            data['short_paper'] = True
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def answer(self, request, pk=None):
        """Record one answer. Deliberately returns no marking.

        Telling the student whether they were right would turn the paper back
        into a quiz, so the response carries only what is needed to keep going.
        """
        from django.utils import timezone
        from .services.timing import answers_are_open, seconds_remaining

        test = self.get_object()
        if test.completed_at:
            return Response({'detail': 'This test has already been submitted.'}, status=400)

        now = timezone.now()
        if not answers_are_open(test.started_at, test.duration_minutes, now):
            return Response({'detail': 'Time is up for this test.',
                             'seconds_remaining': 0}, status=409)

        row = test.paper.filter(id=request.data.get('paper_question_id')).first()
        if row is None:
            return Response({'detail': 'Question not part of this test.'}, status=404)

        row.user_answer = str(request.data.get('answer', ''))
        row.answered_at = now
        row.save(update_fields=['user_answer', 'answered_at'])

        return Response({
            'id': row.id,
            'answered': True,
            'seconds_remaining': seconds_remaining(
                test.started_at, test.duration_minutes, now),
        })

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Grade the whole paper and hand back the full review."""
        from django.db import transaction
        from django.utils import timezone

        test = self.get_object()
        if test.completed_at:
            return Response(self._review(test))

        rows = list(test.paper.select_related('question'))
        # Grading and stamping must land together, or a crash between them would
        # leave a paper that reads as unfinished but is already marked.
        with transaction.atomic():
            correct = 0
            for row in rows:
                row.is_correct = (row.user_answer or '').strip() == \
                    (row.question.correct_answer or '').strip()
                correct += 1 if row.is_correct else 0
            MockTestQuestion.objects.bulk_update(rows, ['is_correct'])

            test.completed_at = timezone.now()
            test.score = round(correct / len(rows) * 100, 1) if rows else 0.0
            test.save(update_fields=['completed_at', 'score'])

        return Response(self._review(test))

    def _review(self, test):
        """The paper with its marking revealed — only ever after submission."""
        rows = test.paper.select_related('question').all()
        return {
            'id': test.id,
            'score': test.score,
            'completed_at': test.completed_at,
            'question_count': test.question_count,
            'correct_count': sum(1 for r in rows if r.is_correct),
            'paper': MockTestQuestionReviewSerializer(rows, many=True).data,
        }
