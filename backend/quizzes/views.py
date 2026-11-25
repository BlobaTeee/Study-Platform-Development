import logging

from django.db.models import Q
from rest_framework import viewsets, permissions, status
from rest_framework.exceptions import PermissionDenied
from notebooks.services.membership import can_edit_item, notebooks_for
from rest_framework.decorators import action
from django.utils.translation import gettext as _
from studyplatform.throttling import GenerationRateThrottle
from rest_framework.response import Response
from rest_framework.views import APIView
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
from .services.topup import TOPUP_PER_ROUND, questions_to_request, should_continue

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
        mine = Quiz.objects.filter(user=self.request.user, is_published=True)
        shared = Quiz.objects.filter(is_published=True,
                                     sources__notebook__in=notebooks_for(self.request.user))
        if self.request.method not in permissions.SAFE_METHODS:
            return (mine | shared).distinct()
        return (mine | shared | Quiz.objects.filter(is_public=True, is_published=True)).distinct()

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
        # Questions of own quizzes and of quizzes in shared notebooks;
        # `can_edit_item` gates the writes below.
        return Question.objects.filter(
            Q(quiz__user=self.request.user)
            | Q(quiz__sources__notebook__in=notebooks_for(self.request.user))
        ).distinct()

    def perform_update(self, serializer):
        self._refuse_unless_editable(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._refuse_unless_editable(instance)
        instance.delete()

    def _refuse_unless_editable(self, question):
        if not can_edit_item(question, self.request.user):
            raise PermissionDenied(_('Only the person who made this question, or the notebook owner, '
                                     'can change it.'))

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

    from notebooks.services.generate import generate_more_questions

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
        want = questions_to_request(len(pool), requested, per_round_max=TOPUP_PER_ROUND)
        if want <= 0:
            break
        previous_size = len(pool)
        rounds += 1
        # Told what the pool already asks, and reading passages earlier rounds
        # did not: each round adds to the pool rather than rewording it.
        asked = list(Question.objects.filter(id__in=[q['id'] for q in pool])
                     .values_list('question_text', flat=True))
        try:
            generate_more_questions(sources, user, want, asked, round_no=rounds - 1,
                                    max_count=TOPUP_PER_ROUND)
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
                .filter(Q(quiz__is_published=True, quiz__sources__in=source_ids)
                        & (Q(quiz__user=user) | Q(quiz__sources__notebook__in=notebooks_for(user))))
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


def _owed_question_ids(user, notebook) -> set[int]:
    """The notebook's questions this student has missed and not yet cleared
    (see services.mistakes for the rule). Evidence is every graded answer in
    a quiz attempt, a submitted mock test or a live round; a mock-test row is
    dated by the sitting, since a skipped question has no answered_at of its own.
    """
    from .services.mistakes import owed_question_ids
    in_notebook = {'question__quiz__sources__notebook': notebook}
    quiz_events = (Answer.objects
                   .filter(quiz_attempt__user=user, **in_notebook)
                   .values_list('question_id', 'answered_at', 'is_correct'))
    test_events = (MockTestQuestion.objects
                   .filter(mock_test__user=user, mock_test__completed_at__isnull=False,
                           question__isnull=False, **in_notebook)
                   .values_list('question_id', 'mock_test__completed_at', 'is_correct'))
    from live.models import LiveAnswer
    live_events = (LiveAnswer.objects
                   .filter(user=user, question__isnull=False, **in_notebook)
                   .values_list('question_id', 'answered_at', 'is_correct'))
    return owed_question_ids([*quiz_events.distinct(), *test_events.distinct(), *live_events.distinct()])


class MistakeBankView(APIView):
    """What the student still owes in one notebook — the questions, never
    their answers, so the list can't double as a crib sheet."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from notebooks.models import Notebook
        notebook = notebooks_for(request.user).filter(
            id=request.query_params.get('notebook')).first()
        if notebook is None:
            return Response({'detail': _('Notebook not found.')}, status=404)
        owed = _owed_question_ids(request.user, notebook)
        rows = (Question.objects.filter(id__in=owed)
                .values('id', 'question_text', 'source_id', 'source__title'))
        return Response({'count': len(owed), 'questions': [
            {'id': r['id'], 'question_text': r['question_text'],
             'source': {'id': r['source_id'], 'title': r['source__title']}}
            for r in rows]})


class MistakeRedoView(APIView):
    """Redoing one notebook's missed questions like a quiz, one at a time
    with the answer right after, not as a timed mock test (the user found
    the test oddly formal for going over mistakes, 2026-11-25).

    GET ?notebook=: the owed questions, without their answers, so the list
    is still no crib sheet. POST {notebook, question_id, answer}: marks one,
    records it as quiz evidence for the mistake bank, and says whether it
    has now left the bank (two right in a row)."""
    permission_classes = [permissions.IsAuthenticated]

    def _notebook(self, request, raw):
        return notebooks_for(request.user).filter(id=raw).first()

    def get(self, request):
        notebook = self._notebook(request, request.query_params.get('notebook'))
        if notebook is None:
            return Response({'detail': _('Notebook not found.')}, status=404)
        owed = _owed_question_ids(request.user, notebook)
        questions = Question.objects.filter(id__in=owed).order_by('id')
        return Response({'notebook': {'id': notebook.id, 'title': notebook.title}, 'questions': [
            {'id': q.id, 'question_text': q.question_text, 'question_type': q.question_type,
             'options': q.options} for q in questions]})

    def post(self, request):
        from django.utils import timezone
        notebook = self._notebook(request, request.data.get('notebook'))
        if notebook is None:
            return Response({'detail': _('Notebook not found.')}, status=404)
        question = Question.objects.filter(id=request.data.get('question_id'),
                                           quiz__sources__notebook=notebook).distinct().first()
        if question is None:
            return Response({'detail': _('Question not part of this quiz.')}, status=404)
        answer = str(request.data.get('answer') or '')
        if not answer:
            return Response({'detail': _('Pick an answer first.')}, status=400)
        is_correct = answer == question.correct_answer
        now = timezone.now()
        attempt = (QuizAttempt.objects.filter(user=request.user, quiz=question.quiz, is_redo=True,
                                              started_at__date=timezone.localdate())
                   .first()
                   or QuizAttempt.objects.create(user=request.user, quiz=question.quiz, is_redo=True))
        Answer.objects.create(quiz_attempt=attempt, question=question, user_answer=answer,
                              is_correct=is_correct, points_earned=int(is_correct))
        answers = attempt.answers.all()
        attempt.total_points = answers.count()
        attempt.score = answers.filter(is_correct=True).count() / attempt.total_points * 100
        attempt.is_completed, attempt.completed_at = True, now
        attempt.save(update_fields=['total_points', 'score', 'is_completed', 'completed_at'])
        return Response({'is_correct': is_correct, 'correct_answer': question.correct_answer,
                         'explanation': question.explanation or '',
                         'cleared': question.id not in _owed_question_ids(request.user, notebook)})


class MistakeSummaryView(APIView):
    """How many questions each notebook still owes, for the review list on
    the Progress page. Notebooks with nothing owed are left out."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        rows = []
        for notebook in notebooks_for(request.user).order_by('title'):
            count = len(_owed_question_ids(request.user, notebook))
            if count:
                rows.append({'notebook_id': notebook.id, 'title': notebook.title, 'count': count})
        return Response({'notebooks': rows})


class WeakConceptsView(APIView):
    """The mistake bank grouped into named concepts, biggest first."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from notebooks.models import Notebook
        from .services.concepts import concepts_for
        notebook = notebooks_for(request.user).filter(
            id=request.query_params.get('notebook')).first()
        if notebook is None:
            return Response({'detail': _('Notebook not found.')}, status=404)
        owed = _owed_question_ids(request.user, notebook)
        questions = Question.objects.filter(id__in=owed).order_by('id')
        return Response({'concepts': concepts_for(questions, user=request.user)})


class MisconceptionsView(APIView):
    """What the student keeps confusing, per notebook (services/misconceptions)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .services.misconceptions import misconceptions
        notebooks, pending = misconceptions(request.user)
        # Cards and source ids are for the practice press, not for display.
        for nb in notebooks:
            nb['items'] = [{k: v for k, v in item.items() if k not in ('cards', 'source_ids')}
                           for item in nb['items']]
        return Response({'notebooks': notebooks, 'pending': pending})


class MisconceptionPracticeView(APIView):
    """Make one misconception's contrast cards (once) and return their ids."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from flashcards.models import Flashcard
        from .services.misconceptions import find_item
        notebook = notebooks_for(request.user).filter(id=request.data.get('notebook_id')).first()
        if notebook is None:
            return Response({'detail': _('Notebook not found.')}, status=404)
        item = find_item(request.user, notebook.id, str(request.data.get('key') or ''))
        if item is None or not item['cards']:
            return Response({'detail': _('That mix-up is no longer on the list.')}, status=404)
        # Pressed twice, the same cards: found by their questions in this notebook.
        existing = {c.question: c.id for c in Flashcard.objects.filter(
            user=request.user, notebook=notebook, archived=False,
            question__in=[c['question'] for c in item['cards']])}
        ids = []
        for card in item['cards']:
            if card['question'] in existing:
                ids.append(existing[card['question']])
                continue
            made = Flashcard.objects.create(user=request.user, notebook=notebook, question=card['question'],
                                            answer=card['answer'], explanation=item['difference'],
                                            is_public=False)
            made.sources.set(item['source_ids'])
            ids.append(made.id)
        return Response({'card_ids': ids})


class PracticeConceptView(APIView):
    """Write a fresh five-question paper on one weak concept."""
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [GenerationRateThrottle]

    def post(self, request):
        from notebooks.models import Notebook
        from .services.practice import PracticeUnavailable, generate_practice_quiz
        notebook = notebooks_for(request.user).filter(id=request.data.get('notebook')).first()
        if notebook is None:
            return Response({'detail': _('Notebook not found.')}, status=404)
        ids = request.data.get('question_ids') or []
        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids) or not ids:
            return Response({'detail': _('question_ids must be a non-empty list.')}, status=400)
        # Only this student's own missed questions in this notebook can seed a
        # paper — anything else is a 400, not a peek at someone's questions.
        allowed = _owed_question_ids(request.user, notebook)
        if not set(ids) <= allowed:
            return Response({'detail': _('Those questions are not in your mistake bank for this notebook.')},
                            status=400)
        questions = list(Question.objects.filter(id__in=ids).select_related('source').order_by('id'))
        label = (str(request.data.get('label') or '')).strip()[:80] or _('a weak concept')
        key = (str(request.data.get('key') or '')).strip()[:12]

        def payload(quiz):
            return {'quiz_id': quiz.id, 'question_count': quiz.questions.count(),
                    'source_ids': sorted(quiz.sources.values_list('id', flat=True))}

        # One live practice quiz per concept: a second press reopens it.
        if key:
            existing = Quiz.objects.filter(user=request.user, is_published=True, practice_key=key).first()
            if existing is not None:
                return Response(payload(existing), status=200)
        try:
            quiz = generate_practice_quiz(request.user, notebook, label, questions, key=key)
        except PracticeUnavailable as exc:
            return Response({'detail': str(exc)}, status=503)
        return Response(payload(quiz), status=201)


def _parts_summary(rows) -> list[dict]:
    parts: dict[str, dict] = {}
    for row in rows:
        part = parts.setdefault(row.section, {'section': row.section, 'count': 0, 'points': 0.0, 'earned': 0.0})
        part['count'] += 1
        part['points'] = round(part['points'] + row.points, 2)
        part['earned'] = round(part['earned'] + (row.earned or 0), 2)
    return list(parts.values())


def _mark_exam_row(row) -> None:
    """Set is_correct, earned and (for a written answer) grade on one row of
    an exam-shaped paper. Never raises: a part the model cannot mark earns
    nothing and says so, rather than leaving the paper unsubmitted."""
    from .services.exam import parse_marks, tf_earned, written_earned
    if row.section == 'true_false':
        row.earned, right = tf_earned(parse_marks(row.user_answer), row.statements, row.points)
        row.is_correct = right == len(row.statements)
    elif row.section == 'short' and (row.reference or {}).get('answer'):
        # A real paper's answer (services/sitting.py): as practice checks it,
        # against the printed answer and the other ways of writing it.
        from exercises.services.grading import short_matches
        ref = row.reference
        row.is_correct = short_matches(row.user_answer, [str(ref['answer']), *ref.get('accept', [])])
        row.earned = row.points if row.is_correct else 0.0
    elif row.section == 'short':
        verdict = 'wrong'
        if row.user_answer.strip():
            try:
                from .services.typed_grading import grade_typed
                verdict = grade_typed(row, row.user_answer)['verdict']
            except Exception:  # noqa: BLE001 - the scorer is missing: fall back to exact match
                verdict = 'correct' if _answer_matches(row.user_answer, row.correct_answer) else 'wrong'
        row.is_correct = verdict == 'correct'
        row.earned = row.points if row.is_correct else 0.0
    elif row.section == 'written':
        from exercises.models import Exercise
        from exercises.services import grading
        from exercises.services.common import PracticeUnavailable, split_sentences
        sentences = split_sentences(row.user_answer)
        if not sentences:
            row.grade, row.earned, row.is_correct = {'verdict': 'needs_work', 'met': []}, 0.0, False
            return
        # Marked once and never again, so it waits for an answer: the normal
        # lane, and one more try. A failure here would cost the part's points.
        exercise = Exercise(prompt=row.question_text, reference=row.reference)
        result = None
        for _ in range(2):
            try:
                result = grading.grade(exercise, sentences, quick=False)
                break
            except PracticeUnavailable:
                continue
        if result is None:
            row.grade, row.earned, row.is_correct = {'not_graded': True}, 0.0, False
            return
        row.grade = {**result, 'sentences': sentences}
        row.earned = written_earned(result, len((row.reference or {}).get('checkpoints', [])), row.points)
        row.is_correct = result.get('verdict') == 'passed'
    else:
        row.is_correct = _answer_matches(row.user_answer, row.correct_answer)
        row.earned = row.points if row.is_correct else 0.0


def _send_misses_back(test, rows) -> None:
    """A real paper's problems missed in the sitting are due again in
    practice today, so they come up under "to review today"."""
    from django.utils import timezone
    from exercises.models import Exercise
    missed = [(r.reference or {}).get('exercise_id') for r in rows if not r.is_correct]
    Exercise.objects.filter(user=test.user, id__in=[m for m in missed if m]).update(
        status='revisit', revisit_on=timezone.localdate())


def _exam_paper(user, notebook, source_ids, tpl):
    """The rows of an exam-shaped paper (services/exam.py), in part order, and
    what fell short: ([row fields], {"missing": [kinds], "generated": bool}).

    Parts I and III come from the multiple-choice bank (III only from
    questions whose answer is short enough to type); Part II from the
    notebook's true/false items, written by the model when there are too few;
    Part IV from the student's practice problems on this notebook, one made
    when there is none."""
    import random
    from exercises.models import Exercise
    from exercises.services import problems as practice
    from exercises.services.common import PracticeUnavailable
    from .models import TrueFalseItem
    from .services.exam import suits_typing, write_true_false

    want = {kind: (count, points) for kind, count, points in tpl['parts']}
    generated = False
    rows: dict[str, list[dict]] = {kind: [] for kind in want}

    need_mc = sum(want.get(k, (0, 0))[0] for k in ('choice', 'short'))
    if need_mc:
        pool = _question_pool(user, source_ids)
        if len(pool) < need_mc:
            pool, generated = _top_up_pool(user, notebook, source_ids, pool, need_mc)
        by_id = {q.id: q for q in Question.objects.filter(id__in=[e['id'] for e in pool],
                                                           question_type='multiple_choice')}
        pool = [e for e in pool if e['id'] in by_id]
        weights = source_weights(_source_accuracy(user, source_ids))
        taken: set[int] = set()
        for kind in ('short', 'choice'):
            if kind not in want:
                continue
            fits = [e for e in pool if e['id'] not in taken
                    and (kind == 'choice' or suits_typing(by_id[e['id']].correct_answer))]
            for entry in sample_paper(fits, weights, count=want[kind][0]):
                q = by_id[entry['id']]
                taken.add(q.id)
                rows[kind].append({'question_id': q.id, 'question_text': q.question_text, 'options': q.options,
                                   'correct_answer': q.correct_answer, 'explanation': q.explanation,
                                   'source_id': q.source_id, 'source_excerpt': q.source_excerpt})

    if 'true_false' in want:
        count = want['true_false'][0]
        bank = list(TrueFalseItem.objects.filter(notebook=notebook))
        if len(bank) < count:
            made = write_true_false(notebook, count - len(bank) + 2)
            generated = generated or bool(made)
            bank += made
        for item in random.sample(bank, min(count, len(bank))):
            rows['true_false'].append({'question_text': item.stem, 'statements': item.statements,
                                       'source_id': item.source_id,
                                       'source_excerpt': ' … '.join(st.get('basis', '') for st in item.statements)})

    if 'written' in want:
        mine = list(Exercise.objects.filter(user=user, notebook=notebook, origin='document'))
        if not mine:
            source = next((src for src in notebook.sources.all() if (src.extracted_text or '').strip()), None)
            if source is not None:
                try:
                    mine = practice.from_document(user, source)
                    generated = True
                except PracticeUnavailable:
                    mine = []
        for ex in random.sample(mine, min(want['written'][0], len(mine))):
            rows['written'].append({'question_text': ex.prompt, 'reference': ex.reference,
                                    'source_id': ex.source_id})

    paper = []
    for kind, _count, points in tpl['parts']:
        for fields in rows[kind]:
            paper.append({**fields, 'section': kind, 'points': points})
    missing = [kind for kind, count, _ in tpl['parts'] if len(rows[kind]) < count]
    return paper, {'missing': missing, 'generated': generated}


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

        notebook = notebooks_for(request.user).filter(
            id=request.data.get('notebook')).first()
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
        mistakes_only = bool(request.data.get('mistakes_only'))
        generated = False
        name = str(request.data.get('template') or '')
        if name and not mistakes_only and plan is None:
            return self._create_exam(request, notebook, source_ids, name)
        if mistakes_only:
            # A retake paper is exactly the bank, however long that is: no
            # top-up (new questions were never missed) and no cap, so the
            # student clears the whole thing in one sitting.
            owed = _owed_question_ids(request.user, notebook)
            if not owed:
                return Response(
                    {'detail': _('Nothing in the mistake bank for this notebook yet.')},
                    status=400)
            pool = [{'id': qid, 'source_ids': []} for qid in owed]
            requested = len(pool)
        else:
            pool = _question_pool(request.user, source_ids)
            # Top up before judging the pool, not after: a notebook whose
            # documents have never been made into a quiz can now still be
            # sat, which is the case this used to reject outright.
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
                    source_id=questions_by_id[entry['id']].source_id,
                    source_excerpt=questions_by_id[entry['id']].source_excerpt,
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

    def _create_exam(self, request, notebook, source_ids, name):
        """Start a sitting in an exam's shape (services/exam.py TEMPLATES)."""
        from django.db import transaction
        from .services.exam import template

        tpl = template(name)
        if tpl is None:
            return Response({'detail': _('Unknown test format.')}, status=400)
        paper, info = _exam_paper(request.user, notebook, source_ids, tpl)
        if not paper:
            return Response(
                {'detail': _('No questions could be generated for this notebook. '
                             'Check its documents have finished processing, then '
                             'try generating a quiz from them.')},
                status=400,
            )
        with transaction.atomic():
            test = MockTest.objects.create(user=request.user, notebook=notebook, template=name,
                                           question_count=len(paper), duration_minutes=tpl['duration'])
            MockTestQuestion.objects.bulk_create([
                MockTestQuestion(mock_test=test, order=i, **fields) for i, fields in enumerate(paper)
            ])
        test = self.get_queryset().get(pk=test.pk)
        data = MockTestSerializer(test).data
        if info['missing']:
            data['short_paper'] = True
            data['missing_parts'] = info['missing']
        if info['generated']:
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
        if isinstance(raw_answer, dict):
            # A true/false question's marks, {label: bool}, kept as JSON.
            import json
            raw_answer = json.dumps({str(k): v for k, v in raw_answer.items() if isinstance(v, bool)})
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
        if test.template:
            return self._submit_exam(test)

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

    def _submit_exam(self, test):
        """Mark an exam-shaped paper part by part. Typed and written answers
        may ask the model, so they are marked before the row lock is taken;
        the lock then only guards stamping the result once."""
        from django.db import transaction
        from django.utils import timezone

        rows = list(test.paper.all())
        for row in rows:
            _mark_exam_row(row)
        with transaction.atomic():
            locked = MockTest.objects.select_for_update().get(pk=test.pk)
            if locked.completed_at:
                return Response(self._review(locked))
            MockTestQuestion.objects.bulk_update(rows, ['is_correct', 'earned', 'grade'])
            total = sum(r.points for r in rows)
            locked.completed_at = timezone.now()
            locked.score = round(sum(r.earned or 0 for r in rows) / total * 100, 1) if total else 0.0
            locked.save(update_fields=['completed_at', 'score'])
            if locked.template == 'paper':
                _send_misses_back(locked, rows)
        return Response(self._review(locked, rows))

    @action(detail=True, methods=['post'])
    def explain(self, request, pk=None):
        """'Why?' on one wrong answer of a submitted paper."""
        from .services.explain import ExplainUnavailable, explain_miss

        test = self.get_object()
        if not test.completed_at:
            return Response({'detail': _('Submit the paper first.')}, status=400)
        row = test.paper.filter(id=request.data.get('paper_question_id')).first()
        if row is None:
            return Response({'detail': _('Question not part of this paper.')}, status=404)
        if row.is_correct:
            return Response({'detail': _('That answer was right.')}, status=400)
        try:
            return Response({'id': row.id, 'explanation': explain_miss(row)})
        except ExplainUnavailable as exc:
            return Response({'detail': str(exc)}, status=503)

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
            'notebook': test.notebook_id,
            'paper_title': test.paper_title,
            'score': test.score,
            'completed_at': test.completed_at,
            'question_count': test.question_count,
            'correct_count': sum(1 for r in rows if r.is_correct),
            # What the bank holds now, this sitting included — the review
            # can say "N questions to redo" without a second request.
            # A real paper's misses went back to practice (_send_misses_back).
            'mistake_count': (sum(1 for r in rows if not r.is_correct) if test.notebook is None
                              else len(_owed_question_ids(test.user, test.notebook))),
            'paper': MockTestQuestionReviewSerializer(rows, many=True).data,
            'template': test.template,
            # Points per part of an exam-shaped paper, in part order; empty for
            # a classic paper, which counts questions.
            'parts': _parts_summary(rows) if test.template else [],
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
