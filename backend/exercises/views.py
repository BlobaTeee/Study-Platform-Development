from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser
from rest_framework.views import APIView

from notebooks.models import Source
from notebooks.services.membership import notebooks_for
from studyplatform.throttling import GenerationRateThrottle

from .models import Exercise
from .services import grading, photo, problems
from .services import figures
from .services.common import PracticeUnavailable, answer_from


def summary(exercise: Exercise) -> dict:
    """A problem as a list shows it: never the rubric."""
    due = exercise.status == 'revisit' and exercise.revisit_on and exercise.revisit_on <= timezone.localdate()
    return {'id': exercise.id, 'notebook_id': exercise.notebook_id, 'source_id': exercise.source_id,
            'origin': exercise.origin, 'prompt': exercise.prompt, 'difficulty': exercise.difficulty,
            # Where it came from, for the one list that holds every problem.
            'notebook_title': exercise.notebook.title if exercise.notebook else '',
            'source_title': exercise.source.title if exercise.source else '',
            'status': exercise.status, 'revisit_on': exercise.revisit_on, 'due': bool(due),
            # Picked together from one file: the list shows them as one set.
            'set_key': exercise.set_key, 'set_title': exercise.set_title,
            # Started but not yet solved, so a list does not call it untouched.
            'attempted': exercise.status == 'new' and grading.round_attempts(exercise).filter(kind='submit').exists(),
            'created_at': exercise.created_at}


def detail(exercise: Exercise) -> dict:
    ref = exercise.reference or {}
    attempts = [{'id': a.id, 'kind': a.kind, 'steps': a.steps, 'result': a.result, 'created_at': a.created_at}
                for a in grading.round_attempts(exercise)]
    is_open = grading.solution_open(exercise)
    failed = grading.failed_submits(exercise)
    met = set()
    for a in attempts:
        if a['kind'] == 'submit':
            met |= set(a['result'].get('met') or [])
    checkpoints = ref.get('checkpoints', [])
    kind = problems.answer_kind(exercise)
    return {
        **summary(exercise),
        'attempts': attempts,
        'answer_kind': kind,
        # What to choose from; which is right stays hidden until it is open.
        'options': [{'label': o['label'], 'text': o['text']} for o in ref.get('options', [])] if kind == 'choice' else [],
        'statements': [{'label': st['label'], 'text': st['text']} for st in ref.get('statements', [])]
        if kind == 'true_false' else [],
        'answer_key': _answer_key(ref, kind) if is_open else None,
        'answer_format': problems.answer_format(exercise),
        'figures': exercise.figures or [],
        'set': _set_position(exercise),
        'checkpoint_count': len(checkpoints),
        # Reached checkpoints are named, as feedback; the rest stay hidden.
        'met_checkpoints': [c for c in checkpoints if c['id'] in met] if not is_open else checkpoints,
        'failed_submits': failed,
        'can_reveal': not is_open and failed >= grading.REVEAL_AFTER,
        'solution': ref.get('solution', []) if is_open else None,
        'mistakes': ref.get('mistakes', []) if is_open else None,
    }


def _set_position(exercise: Exercise) -> dict | None:
    """Where the problem stands in the set it was picked with, or among the
    problems written from the same document (the list shows either as one
    row), for "3 of 8" and the way to the next; None for one on its own."""
    if exercise.set_key:
        group = Exercise.objects.filter(user_id=exercise.user_id, set_key=exercise.set_key)
    elif exercise.origin == 'document' and exercise.source_id:
        group = Exercise.objects.filter(user_id=exercise.user_id, origin='document', set_key='',
                                        source_id=exercise.source_id)
    else:
        return None
    ids = list(group.order_by('id').values_list('id', flat=True))
    if len(ids) < 2 or exercise.id not in ids:
        return None
    at = ids.index(exercise.id)
    return {'index': at + 1, 'total': len(ids),
            'prev_id': ids[at - 1] if at > 0 else None, 'next_id': ids[at + 1] if at + 1 < len(ids) else None}


def _answer_key(ref: dict, kind: str) -> dict | None:
    if kind == 'choice':
        return {'answer': ref.get('answer')}
    if kind == 'true_false':
        return {'answers': {st['label']: st['answer'] for st in ref.get('statements', [])}}
    if kind == 'short':
        return {'answer': ref.get('answer')}
    return None


def _given(exercise: Exercise, data) -> tuple[object, str]:
    """The answer to a keyed problem from the request, and an error if it is
    not one: a choice is one of the options' labels, true/false marks every
    statement, a short answer is some text."""
    ref = exercise.reference or {}
    kind = problems.answer_kind(exercise)
    answer = data.get('answer')
    if kind == 'choice':
        labels = {o['label'] for o in ref.get('options', [])}
        return (answer, '') if answer in labels else (None, _('Pick one of the options first.'))
    if kind == 'true_false':
        labels = [st['label'] for st in ref.get('statements', [])]
        if not isinstance(answer, dict) or any(not isinstance(answer.get(lb), bool) for lb in labels):
            return None, _('Mark every statement true or false first.')
        return {lb: answer[lb] for lb in labels}, ''
    text = str(data.get('text') or '').strip()[:problems.MAX_SHORT_ANSWER * 2]
    return (text, '') if text else (None, _('Write your answer first.'))


def _mine(request, pk) -> Exercise:
    exercise = get_object_or_404(Exercise.objects.select_related('notebook', 'source'), pk=pk, user=request.user)
    grading.start_due_revisit(exercise)
    return exercise


class _Generating(APIView):
    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        if self.request.method == 'POST':
            return [GenerationRateThrottle()]
        return super().get_throttles()


class SetView(APIView):
    """PATCH {title} → the set renamed; an empty title gives back the
    default name the list shows."""
    permission_classes = [IsAuthenticated]

    def patch(self, request, key):
        title = str(request.data.get('title') or '').strip()[:200]
        changed = Exercise.objects.filter(user=request.user, set_key=key).exclude(set_key='').update(set_title=title)
        if not changed:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response({'set_key': key, 'set_title': title})


class ExerciseListView(APIView):
    """GET ?notebook=&source= → the student's problems, oldest first;
    ?own=1 → only the problems they brought themselves."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Exercise.objects.filter(Q(notebook__in=notebooks_for(request.user)) | Q(notebook__isnull=True),
                                     user=request.user).select_related('notebook', 'source')
        if request.query_params.get('own') == '1':
            qs = qs.filter(origin='own')
        for param, field in (('notebook', 'notebook_id'), ('source', 'source_id')):
            value = request.query_params.get(param)
            if value and value.isdigit():
                qs = qs.filter(**{field: int(value)})
        return Response({'results': [summary(e) for e in qs]})


class GenerateView(_Generating):
    """POST {source_id} → three problems written from that document."""

    def post(self, request):
        source = get_object_or_404(Source, pk=request.data.get('source_id'),
                                   notebook__in=notebooks_for(request.user))
        try:
            made = problems.from_document(request.user, source)
        except PracticeUnavailable as exc:
            return Response({'detail': str(exc)}, status=503)
        return Response({'results': [summary(e) for e in made]}, status=status.HTTP_201_CREATED)


class OwnProblemView(_Generating):
    """POST {text} → the student's own problem, with a rubric. It belongs to
    no notebook: it is graded from general knowledge, not a document."""

    def post(self, request):
        text = str(request.data.get('text') or '').strip()[:problems.MAX_OWN_CHARS]
        if len(text) < problems.MIN_OWN_CHARS:
            return Response({'detail': _('Write out the whole problem, with everything it gives.')}, status=400)
        try:
            exercise = problems.own_problem(request.user, text)
        except problems.IncompleteProblem as exc:
            return Response({'detail': str(exc), 'incomplete': True}, status=400)
        except PracticeUnavailable as exc:
            return Response({'detail': str(exc)}, status=503)
        return Response(detail(exercise), status=status.HTTP_201_CREATED)


class OwnSetView(_Generating):
    """POST {texts: [...], figures: [[data URL | null, ...], ...], title} →
    several of the student's own problems, picked together from one photo or
    file, as one set: {results, skipped}. figures[i] are problem i's, as
    read; title names the set (the file's name); answers[i] is problem i's
    answer from a Word file's key table, or null; hints[i] the key as the
    model read it from a picture, which may be misread, or null."""

    def post(self, request):
        raw = request.data.get('texts')
        texts = [str(t or '').strip() for t in raw] if isinstance(raw, list) else []
        if not texts or len(texts) > problems.MAX_SET:
            return Response({'detail': _('Pick between 1 and %(max)d problems.') % {'max': problems.MAX_SET}},
                            status=400)
        if any(len(t) < problems.MIN_OWN_CHARS for t in texts):
            return Response({'detail': _('Write out the whole problem, with everything it gives.')}, status=400)
        # Each problem's figures as read (figures.cut), checked again: they
        # come back from the browser.
        given = request.data.get('figures') if isinstance(request.data.get('figures'), list) else []
        cut = [[figures.clean(f) for f in (g if isinstance(g, list) else [])][:figures.MAX_PER_QUESTION]
               for g in given[:len(texts)]]
        try:
            given_answers = request.data.get('answers') if isinstance(request.data.get('answers'), list) else []
            given_hints = request.data.get('hints') if isinstance(request.data.get('hints'), list) else []
            made, skipped = problems.own_set(request.user, texts, cut,
                                             str(request.data.get('title') or ''), given_answers[:len(texts)],
                                             given_hints[:len(texts)])
        except problems.IncompleteProblem as exc:
            return Response({'detail': str(exc), 'incomplete': True}, status=400)
        except PracticeUnavailable as exc:
            return Response({'detail': str(exc)}, status=503)
        return Response({'results': [summary(e) for e in made], 'skipped': skipped},
                        status=status.HTTP_201_CREATED)


class ReadPhotoView(_Generating):
    """POST multipart {image} → {questions: [{label, instruction, text}]}: the
    photographed questions as text, for the student to pick one and check it
    before creating it. The photo is not kept."""
    parser_classes = [MultiPartParser]

    def post(self, request):
        upload = request.FILES.get('image')
        if upload is None:
            return Response({'detail': _('Choose a photo of the problem.')}, status=400)
        if upload.size > photo.max_bytes():
            return Response({'detail': _('That file is too large. Use one under 15 MB.')}, status=400)
        data = upload.read()
        try:
            questions, title = photo.read_problems(data)
        except photo.NotAnImage as exc:
            return Response({'detail': str(exc)}, status=400)
        except photo.NoProblemInPhoto as exc:
            return Response({'detail': str(exc), 'no_problem': True}, status=400)
        except PracticeUnavailable as exc:
            return Response({'detail': str(exc)}, status=503)
        return Response({'questions': questions, 'title': title})


class ExerciseDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        return Response(detail(_mine(request, pk)))

    def delete(self, request, pk):
        _mine(request, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SubmitView(_Generating):
    """POST {text} (or {steps}) → the attempt graded against the rubric; for
    a choice, true/false or short problem, {answer} or {text} checked against
    its key."""

    def get_throttles(self):
        # A keyed answer costs no model request, so it does not count
        # towards the allowance for AI work.
        mine = Exercise.objects.filter(pk=self.kwargs.get('pk'), user=self.request.user).first()
        if mine is not None and problems.answer_kind(mine) in problems.KEYED_KINDS:
            return []
        return super().get_throttles()

    def post(self, request, pk):
        exercise = _mine(request, pk)
        if problems.answer_kind(exercise) in problems.KEYED_KINDS:
            given, problem = _given(exercise, request.data)
            if problem:
                return Response({'detail': problem}, status=400)
            grading.check(exercise, given)
            exercise.refresh_from_db()
            return Response(detail(exercise), status=status.HTTP_201_CREATED)
        steps, text = answer_from(request.data)
        if not steps:
            return Response({'detail': _('Write your answer first.')}, status=400)
        try:
            grading.submit(exercise, steps, text)
        except PracticeUnavailable as exc:
            return Response({'detail': str(exc)}, status=503)
        exercise.refresh_from_db()
        return Response(detail(exercise), status=status.HTTP_201_CREATED)


class HintView(_Generating):
    """POST {text} (or {steps}) → one guiding question for where the student is stuck."""

    def post(self, request, pk):
        exercise = _mine(request, pk)
        steps, text = answer_from(request.data)
        try:
            grading.hint(exercise, steps, text)
        except PracticeUnavailable as exc:
            return Response({'detail': str(exc)}, status=503)
        return Response(detail(exercise), status=status.HTTP_201_CREATED)


class RevealView(APIView):
    """POST → the model solution, once enough submits have failed."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        exercise = _mine(request, pk)
        if not grading.solution_open(exercise):
            if grading.failed_submits(exercise) < grading.REVEAL_AFTER:
                return Response({'detail': _('Keep trying a little longer before looking at the solution.')},
                                status=400)
            grading.reveal(exercise)
            exercise.refresh_from_db()
        return Response(detail(exercise))


class MistakesView(APIView):
    """GET → errors made in practice, by notebook and error type."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'notebooks': grading.mistakes_by_notebook(request.user)})
