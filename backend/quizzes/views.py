import logging

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from django.utils.translation import gettext as _
from studyplatform.throttling import GenerationRateThrottle
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
    sample_paper, source_accuracy, source_weights, clamp_int, _answer_matches,
    MIN_QUESTIONS, MAX_QUESTIONS, MIN_DURATION_MINUTES, MAX_DURATION_MINUTES,
)
from .services.topup import questions_to_request, should_continue

logger = logging.getLogger(__name__)


class QuizViewSet(viewsets.ModelViewSet):
    serializer_class = QuizSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['topic', 'is_public', 'is_published']
    search_fields = ['title', 'description']
    ordering_fields = ['created_at', 'title']
    ordering = ['-created_at']

    def get_queryset(self):
        # Retired quizzes (replaced by a regeneration) stay in the database for
        # their attempts, but are not offered to study from.
        return (Quiz.objects.filter(user=self.request.user, is_published=True)
                | Quiz.objects.filter(is_public=True, is_published=True))

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
            return Response({'detail': _('Not allowed.')}, status=status.HTTP_403_FORBIDDEN)
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

    @action(detail=True, methods=['post'])
    def grade_typed_answer(self, request, pk=None):
        """Grade an answer the student typed rather than picked.

        Writes an Answer row like submit_answer does, so `complete` scores
        the attempt unchanged; the row also records how it was graded.
        """
        from .services.typed_grading import grade_typed

        attempt = self.get_object()
        if attempt.is_completed:
            return Response({'detail': _('This attempt is already complete.')}, status=400)
        typed = (request.data.get('answer') or '').strip()
        if not typed:
            return Response({'detail': _('Type an answer first.')}, status=400)
        question = Question.objects.filter(pk=request.data.get('question_id'),
                                           quiz=attempt.quiz).first()
        if question is None:
            return Response({'detail': _('Question not part of this quiz.')}, status=404)

        try:
            verdict = grade_typed(question, typed)
        except Exception:  # noqa: BLE001 — the scorer artifact, most likely
            logger.exception('Typed grading failed')
            return Response({'detail': 'Typed grading is unavailable — build the model with '
                                       '`manage.py ensure_ml_model`.'}, status=503)

        is_correct = verdict['verdict'] == 'correct'
        answer = Answer.objects.create(
            quiz_attempt=attempt, question=question, user_answer=typed,
            is_correct=is_correct, points_earned=1 if is_correct else 0,
            mode='typed', verdict=verdict['verdict'], graded_how=verdict['how'],
        )
        return Response({
            'id': answer.id, 'verdict': verdict['verdict'], 'how': verdict['how'],
            'is_correct': is_correct, 'reference_answer': question.correct_answer,
            'explanation': question.explanation,
        })

    @action(detail=True, methods=['post'])
    def override_answer(self, request, pk=None):
        """The student disagrees with the grader. Their call stands, and the
        disagreement is kept: it is the label the model can learn from."""
        attempt = self.get_object()
        if attempt.is_completed:
            return Response({'detail': _('This attempt is already complete.')}, status=400)
        answer = attempt.answers.filter(id=request.data.get('answer_id')).first()
        if answer is None:
            return Response({'detail': _('Answer not part of this attempt.')}, status=404)
        if answer.mode != 'typed':
            return Response({'detail': _('Only typed answers can be overridden.')}, status=400)
        is_correct = bool(request.data.get('is_correct'))
        answer.is_correct = is_correct
        answer.points_earned = 1 if is_correct else 0
        answer.overridden = True
        answer.save(update_fields=['is_correct', 'points_earned', 'overridden'])
        return Response({'id': answer.id, 'is_correct': is_correct, 'overridden': True})


def _top_up_pool(user, notebook, source_ids, pool, requested):
    """Generate questions until the notebook can fill the paper, or we stop.

    Returns (pool, generated_any). Never raises: a paper that cannot be topped
    up is still a paper, and a student pressing "start" must not be met with a
    provider error. Every failure path leaves the pool exactly as it was.

    Generated questions are written as an ordinary Quiz tagged to these
    sources, so they are not private to this sitting — they join the pool
    permanently and the next test starts faster for having been generated
    here.
    """
    import logging
    import time

    from notebooks.services.generate import generate_quiz_for_sources

    logger = logging.getLogger(__name__)

    # Only documents that finished processing can be generated from;
    # generate_quiz_for_sources raises on anything else, and one still-
    # processing upload must not stop the others being used.
    sources = [s for s in notebook.sources.all()
               if s.status == 'ready' and s.extracted_text.strip()]
    if not sources:
        return pool, False

    started = time.monotonic()
    rounds = 0
    previous_size = -1  # so the "did it grow" test cannot fire on round one
    generated_any = False

    while should_continue(len(pool), previous_size, requested, rounds,
                          time.monotonic() - started):
        want = questions_to_request(len(pool), requested)
        if want <= 0:
            break
        previous_size = len(pool)
        rounds += 1
        try:
            generate_quiz_for_sources(sources, user, question_count=want)
        except Exception as exc:  # noqa: BLE001
            # Includes the provider being down, a quota refusal, and documents
            # too thin to generate from. All of them mean "no more questions
            # today", not "the student cannot sit a test".
            logger.warning('Mock test top-up generation failed: %s', exc)
            break
        generated_any = True
        # Re-resolved rather than appended: this is the same function the
        # paper is built from, so a question that does not show up here would
        # not have been sampled anyway, and counting it would make the loop
        # think it had made progress it had not.
        pool = _question_pool(user, source_ids)

    return pool, generated_any


def _question_pool(user, source_ids):
    """Every question generated from this notebook's documents, each with the
    subset of those documents it came from.

    Filtering and reading `quiz__sources` in the same query reuses one join,
    so the ids that come back are only the selected ones.
    """
    if not source_ids:
        return []
    pool: dict[int, list[int]] = {}
    for row in (Question.objects
                .filter(quiz__user=user, quiz__is_published=True, quiz__sources__in=source_ids)
                .values('id', 'quiz__sources')):
        pool.setdefault(row['id'], []).append(row['quiz__sources'])
    return [{'id': qid, 'source_ids': ids} for qid, ids in pool.items()]


def _source_accuracy(user, source_ids):
    """How well the user has answered questions from this notebook's own
    documents so far — the weighting has no use for accuracy on unrelated
    material, so this is scoped rather than pulling the user's whole history.

    One row per (answer, source): an answer to a question drawn from two of
    the selected documents counts for each, which is what `source_accuracy`
    expects.
    """
    if not source_ids:
        return {}
    rows = [
        {'source_ids': [row['question__quiz__sources']], 'is_correct': row['is_correct']}
        for row in Answer.objects
        .filter(quiz_attempt__user=user, question__quiz__sources__in=source_ids)
        .values('question__quiz__sources', 'is_correct')
    ]
    return source_accuracy(rows)


class MockTestViewSet(viewsets.ModelViewSet):
    """Sit a timed paper drawn from a whole notebook."""
    serializer_class = MockTestSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        # No `paper__question`: the serializers now read straight off
        # MockTestQuestion's own denormalised columns, so following the FK to
        # Question would just be an unused join (and one that skips rows
        # whose question has since gone NULL, which must render as normally
        # as any other).
        return (MockTest.objects.filter(user=self.request.user)
                .select_related('notebook')
                .prefetch_related('paper'))

    def get_throttles(self):
        # Starting a sitting can generate questions to fill the paper (see
        # topup), so it pays the generation rate; everything else on this
        # viewset is a read or an answer save and keeps the default.
        if self.action == 'create':
            return [GenerationRateThrottle()]
        return super().get_throttles()

    def create(self, request, *args, **kwargs):
        from django.db import transaction
        from django.utils import timezone
        from notebooks.models import Notebook

        notebook = Notebook.objects.filter(
            id=request.data.get('notebook'), user=request.user).first()
        if notebook is None:
            return Response({'detail': _('Notebook not found.')}, status=404)

        plan = None
        planned_test_id = request.data.get('planned_test')
        if planned_test_id is not None:
            # Scoped to request.user for the same reason validate_notebook
            # scopes the notebook lookup in serializers.py: a plan id
            # belonging to someone else must fail exactly like a missing
            # one, or the response would let a plan id be enumerated.
            plan = PlannedTest.objects.filter(
                id=planned_test_id, user=request.user).first()
            if plan is None:
                return Response({'detail': _('Planned test not found.')}, status=404)
            if plan.sat_at is not None:
                return Response(
                    {'detail': _('This planned test has already been sat.')}, status=400)
            # Enforced here, not only by the disabled button: the client's
            # clock is the student's to change. `opens_at` lets the client
            # say when rather than just "no" if the two clocks disagree.
            from django.utils import timezone
            from .services.timing import plan_is_open
            if not plan_is_open(plan.scheduled_for, timezone.now()):
                opens = timezone.localtime(plan.scheduled_for)
                return Response({
                    'detail': _('This test opens at %(when)s.') % {'when': f'{opens:%H:%M %d/%m}'},
                    'opens_at': plan.scheduled_for.isoformat(),
                }, status=400)

        # Parse defensively rather than bare int(): a non-numeric value would
        # otherwise raise an unhandled ValueError (500) instead of a 400, and
        # an unclamped count/duration could produce a zero-question paper or
        # an already-expired deadline. See clamp_int's docstring.
        try:
            requested = clamp_int(request.data.get('question_count'),
                                   MIN_QUESTIONS, MAX_QUESTIONS, default=20)
        except ValueError as exc:
            return Response({'detail': _('Number of questions: %(why)s') % {'why': exc}}, status=400)
        try:
            duration = clamp_int(request.data.get('duration_minutes'),
                                  MIN_DURATION_MINUTES, MAX_DURATION_MINUTES, default=30)
        except ValueError as exc:
            return Response({'detail': _('Duration: %(why)s') % {'why': exc}}, status=400)

        source_ids = set(notebook.sources.values_list('id', flat=True))
        pool = _question_pool(request.user, source_ids)

        # Top up before judging the pool, not after: a notebook whose documents
        # have never been made into a quiz can now still be sat, which is the
        # case this used to reject outright.
        generated = False
        if len(pool) < requested:
            pool, generated = _top_up_pool(
                request.user, notebook, source_ids, pool, requested)

        if not pool:
            return Response(
                {'detail': _('No questions could be generated for this notebook. '
                             'Check its documents have finished processing, then '
                             'try generating a quiz from them.')},
                status=400,
            )

        weights = source_weights(_source_accuracy(request.user, source_ids))
        chosen = sample_paper(pool, weights, count=requested)

        # Fetched once, up front, so every field a review will ever need can
        # be copied onto MockTestQuestion below — see the SET_NULL/denormalise
        # comment on that model for why this duplication exists at all.
        questions_by_id = {
            q.id: q for q in Question.objects.filter(
                id__in=[entry['id'] for entry in chosen])
        }

        with transaction.atomic():
            test = MockTest.objects.create(
                user=request.user, notebook=notebook,
                question_count=len(chosen), duration_minutes=duration,
            )
            MockTestQuestion.objects.bulk_create([
                MockTestQuestion(
                    mock_test=test, question_id=entry['id'], order=i,
                    question_text=questions_by_id[entry['id']].question_text,
                    options=questions_by_id[entry['id']].options,
                    correct_answer=questions_by_id[entry['id']].correct_answer,
                    explanation=questions_by_id[entry['id']].explanation,
                )
                for i, entry in enumerate(chosen)
            ])
            if plan is not None:
                # Same transaction as the paper itself: sat_at exists
                # specifically so this link survives the sitting later being
                # deleted (mock_test is SET_NULL and would revert to NULL),
                # so it must never be stamped without the sitting actually
                # having been created, or vice versa.
                plan.mock_test = test
                plan.sat_at = timezone.now()
                plan.save(update_fields=['mock_test', 'sat_at'])

        # Re-fetch through get_queryset() rather than refresh_from_db(): that
        # carries the same select_related/prefetch_related get_queryset()
        # already uses for reads, so the serializer walks the frozen paper's
        # questions in one query instead of one per row.
        test = self.get_queryset().get(pk=test.pk)
        data = MockTestSerializer(test).data
        # Say so rather than silently handing over a shorter paper: the student
        # is about to judge their readiness on it. Still reachable after a
        # top-up — the documents may simply not hold enough material, or the
        # round/time caps may have been hit first.
        if len(chosen) < requested:
            data['short_paper'] = True
        # So the page can explain why starting took as long as it did.
        if generated:
            data['generated_questions'] = True
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
            return Response({'detail': _('This test has already been submitted.')}, status=400)

        now = timezone.now()
        if not answers_are_open(test.started_at, test.duration_minutes, now):
            return Response({'detail': _('Time is up for this test.'),
                             'seconds_remaining': 0}, status=409)

        row = test.paper.filter(id=request.data.get('paper_question_id')).first()
        if row is None:
            return Response({'detail': _('Question not part of this test.')}, status=404)

        # `.get('answer', '')` only falls back to '' when the key is *absent*;
        # a payload of {"answer": null} would otherwise stringify to the
        # literal text "None" and be graded (and shown on the review) as
        # though the student had typed that word.
        raw_answer = request.data.get('answer', '')
        row.user_answer = '' if raw_answer is None else str(raw_answer)
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
        """Grade the whole paper once and hand back the full review.

        Serialised against a concurrent double-submit: two requests racing
        each other block on the row lock below rather than both grading.
        """
        from django.db import transaction
        from django.utils import timezone

        test = self.get_object()
        # Cheap pre-lock check: the common case is a client retrying a submit
        # whose response it never saw, and that case should not pay for a
        # row lock it doesn't need.
        if test.completed_at:
            return Response(self._review(test))

        with transaction.atomic():
            # Re-fetch under select_for_update() and re-check completed_at:
            # without the lock, two simultaneous requests could both read
            # completed_at as unset above and both proceed to grade. The
            # second request to reach this line now blocks until the first
            # commits, then sees completed_at already set and short-circuits
            # instead of re-grading. (Grading happens to be idempotent — it's
            # a pure function of the already-stored answers — but doing it
            # twice is still redundant database work the lock avoids.)
            test = MockTest.objects.select_for_update().get(pk=test.pk)
            if test.completed_at:
                return Response(self._review(test))

            # No select_related('question'): grading reads the paper's own
            # denormalised `correct_answer`, not the live Question, so this
            # still grades correctly even if the source quiz (and therefore
            # `question`) has since been deleted or regenerated.
            rows = list(test.paper.all())
            # Grading and stamping must land together, or a crash between them
            # would leave a paper that reads as unfinished but is already marked.
            correct = 0
            for row in rows:
                row.is_correct = _answer_matches(row.user_answer, row.correct_answer)
                correct += 1 if row.is_correct else 0
            MockTestQuestion.objects.bulk_update(rows, ['is_correct'])

            test.completed_at = timezone.now()
            test.score = round(correct / len(rows) * 100, 1) if rows else 0.0
            test.save(update_fields=['completed_at', 'score'])

        return Response(self._review(test, rows))

    def _review(self, test, rows=None):
        """The paper with its marking revealed — only ever after submission.

        `rows` lets `submit` hand over the paper it just graded rather than
        re-querying it; the already-submitted short-circuit path above has no
        rows loaded, so it is left to query them itself.
        """
        if rows is None:
            rows = test.paper.all()
        return {
            'id': test.id,
            'score': test.score,
            'completed_at': test.completed_at,
            'question_count': test.question_count,
            'correct_count': sum(1 for r in rows if r.is_correct),
            'paper': MockTestQuestionReviewSerializer(rows, many=True).data,
        }


class PlannedTestViewSet(viewsets.ModelViewSet):
    """Tests the student intends to sit, and their reminders."""
    serializer_class = PlannedTestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (PlannedTest.objects.filter(user=self.request.user)
                .select_related('notebook'))

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        old_scheduled_for = serializer.instance.scheduled_for
        plan = serializer.save()
        # A reschedule must not carry over reminder state tied to the old
        # date. reminder_sent_at set means the old date's reminder already
        # fired — leaving it set would mean the new date silently never gets
        # its own. reminder_skipped_at set means send_test_reminders gave up
        # on this plan (its old window passed unsent); the plan just proved
        # that wrong by getting a fresh future date, so it deserves another
        # chance at a reminder rather than staying excluded from the due
        # query forever. Guarded on scheduled_for actually changing so a PATCH
        # that only touches, say, duration_minutes leaves both alone.
        if plan.scheduled_for != old_scheduled_for and (
            plan.reminder_sent_at is not None or plan.reminder_skipped_at is not None
        ):
            plan.reminder_sent_at = None
            plan.reminder_skipped_at = None
            plan.save(update_fields=['reminder_sent_at', 'reminder_skipped_at'])
