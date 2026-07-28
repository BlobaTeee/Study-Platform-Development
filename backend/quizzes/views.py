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
from .services.paper import sample_paper, source_accuracy, source_weights


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


def _question_pool(user, notebook):
    """Every question generated from this notebook's documents.

    Source ids are parsed out of the quiz description rather than matched as a
    substring: `source:3` is a prefix of `source:30`, so substring matching
    would quietly mix in another document's questions.
    """
    from analytics import insights

    source_ids = set(notebook.sources.values_list('id', flat=True))
    if not source_ids:
        return []

    pool = []
    for row in Question.objects.filter(quiz__user=user).values('id', 'quiz__description'):
        matched = [sid for sid in insights.parse_source_ids(row['quiz__description'])
                   if sid in source_ids]
        if matched:
            pool.append({'id': row['id'], 'source_ids': matched})
    return pool


def _source_accuracy(user):
    """How well the user has answered questions from each document so far."""
    from analytics import insights

    rows = [
        {'source_ids': insights.parse_source_ids(row['question__quiz__description']),
         'is_correct': row['is_correct']}
        for row in Answer.objects.filter(quiz_attempt__user=user)
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

        requested = int(request.data.get('question_count', 20))
        duration = int(request.data.get('duration_minutes', 30))
        pool = _question_pool(request.user, notebook)
        if not pool:
            return Response(
                {'detail': 'No quiz questions for this notebook yet. '
                           'Generate a quiz from its documents first.'},
                status=400,
            )

        weights = source_weights(_source_accuracy(request.user))
        chosen = sample_paper(pool, weights, count=requested)

        test = MockTest.objects.create(
            user=request.user, notebook=notebook,
            question_count=len(chosen), duration_minutes=duration,
        )
        MockTestQuestion.objects.bulk_create([
            MockTestQuestion(mock_test=test, question_id=entry['id'], order=i)
            for i, entry in enumerate(chosen)
        ])

        test.refresh_from_db()
        data = MockTestSerializer(test).data
        # Say so rather than silently handing over a shorter paper: the student
        # is about to judge their readiness on it.
        if len(chosen) < requested:
            data['short_paper'] = True
        return Response(data, status=status.HTTP_201_CREATED)
