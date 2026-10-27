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
from .services.common import PracticeUnavailable, clean_steps


def summary(exercise: Exercise) -> dict:
    """A problem as a list shows it: never the rubric."""
    due = exercise.status == 'revisit' and exercise.revisit_on and exercise.revisit_on <= timezone.localdate()
    return {'id': exercise.id, 'notebook_id': exercise.notebook_id, 'source_id': exercise.source_id,
            'origin': exercise.origin, 'prompt': exercise.prompt, 'difficulty': exercise.difficulty,
            # Where it came from, for the one list that holds every problem.
            'notebook_title': exercise.notebook.title if exercise.notebook else '',
            'source_title': exercise.source.title if exercise.source else '',
            'status': exercise.status, 'revisit_on': exercise.revisit_on, 'due': bool(due),
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
    return {
        **summary(exercise),
        'attempts': attempts,
        'checkpoint_count': len(checkpoints),
        # Reached checkpoints are named, as feedback; the rest stay hidden.
        'met_checkpoints': [c for c in checkpoints if c['id'] in met] if not is_open else checkpoints,
        'failed_submits': failed,
        'can_reveal': not is_open and failed >= grading.REVEAL_AFTER,
        'solution': ref.get('solution', []) if is_open else None,
        'mistakes': ref.get('mistakes', []) if is_open else None,
    }


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


class ReadPhotoView(_Generating):
    """POST multipart {image} → {text}: the photographed problem as text, for
    the student to check before creating it. The photo is not kept."""
    parser_classes = [MultiPartParser]

    def post(self, request):
        upload = request.FILES.get('image')
        if upload is None:
            return Response({'detail': _('Choose a photo of the problem.')}, status=400)
        if upload.size > photo.max_bytes():
            return Response({'detail': _('That photo is too large. Use one under 8 MB.')}, status=400)
        data = upload.read()
        try:
            text = photo.read_problem(data)
        except photo.NotAnImage as exc:
            return Response({'detail': str(exc)}, status=400)
        except photo.NoProblemInPhoto as exc:
            return Response({'detail': str(exc), 'no_problem': True}, status=400)
        except PracticeUnavailable as exc:
            return Response({'detail': str(exc)}, status=503)
        return Response({'text': text})


class ExerciseDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        return Response(detail(_mine(request, pk)))

    def delete(self, request, pk):
        _mine(request, pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SubmitView(_Generating):
    """POST {steps} → the attempt graded against the rubric."""

    def post(self, request, pk):
        exercise = _mine(request, pk)
        steps = clean_steps(request.data.get('steps'))
        if not steps:
            return Response({'detail': _('Write at least one step first.')}, status=400)
        try:
            grading.submit(exercise, steps)
        except PracticeUnavailable as exc:
            return Response({'detail': str(exc)}, status=503)
        exercise.refresh_from_db()
        return Response(detail(exercise), status=status.HTTP_201_CREATED)


class HintView(_Generating):
    """POST {steps} → one guiding question for where the student is stuck."""

    def post(self, request, pk):
        exercise = _mine(request, pk)
        try:
            grading.hint(exercise, clean_steps(request.data.get('steps')))
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
