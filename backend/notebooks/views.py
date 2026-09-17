from rest_framework import mixins, viewsets, permissions, status
from rest_framework.decorators import action
from django.utils.translation import gettext as _
from studyplatform.throttling import GenerationRateThrottle
from ml_pipeline.source_guard import InsufficientSourceTextError


def _user_error(exc) -> str:
    """What to tell the student about a failed generation.

    The source guard's message is the one they meet most, so it is restated
    in their language from the numbers the exception carries; provider
    errors are technical and stay as raised.
    """
    if isinstance(exc, InsufficientSourceTextError):
        kind = {'flashcard set': _('flashcard set'), 'quiz': _('quiz')}.get(exc.kind, exc.kind)
        return _('This source is too short to generate a %(kind)s (%(count)s words; '
                 'needs at least %(min)s). Add more text or choose a longer document.') % {
            'kind': kind, 'count': exc.count, 'min': exc.min_words}
    if str(exc) == 'No sources selected.':
        return _('No sources selected.')
    return str(exc)
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.conf import settings
from django.db.models import Prefetch

from .models import Notebook, Source
from .serializers import (
    NotebookSerializer,
    NotebookCreateSerializer,
    SourceSerializer,
)
from .services.document_extract import file_type_from_filename, title_from_filename
from .services.ingest import process_source, finish_text_source
from .services.fetch_page import PageFetchError, fetch_page
from .services.textnorm import normalise_text
from .services.web_source import default_title
from ml_pipeline.source_guard import MIN_WORDS_FLASHCARDS, word_count
from .services.gemini_client import GeminiNotConfiguredError, GeminiGenerationError
from .services.decks import items_with_exact_sources
from .services.generate import (
    generate_flashcards_for_sources,
    generate_quiz_for_sources,
    generate_flashcards_for_source,
    generate_quiz_for_source,
)
from flashcards.models import Flashcard
from flashcards.serializers import FlashcardSerializer
from quizzes.models import Quiz
from quizzes.serializers import QuizSerializer

SUPPORTED_FORMATS = 'PDF, Word (.docx), and PowerPoint (.pptx)'


class NotebookViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        # `defer` matters more than it looks: a plain prefetch_related('sources')
        # loads whole Source rows, and `extracted_text` holds an entire document
        # — 282 KB across three files here. SourceListSerializer never outputs
        # it, so every notebook load was pulling that out of Postgres and
        # discarding it, growing with each upload.
        return Notebook.objects.filter(user=self.request.user).prefetch_related(
            Prefetch('sources', queryset=Source.objects.defer('extracted_text'))
        )

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return NotebookCreateSerializer
        return NotebookSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def add_text(self, request, pk=None):
        """A source from pasted text: no file, ready at once."""
        notebook = self.get_object()
        text = normalise_text(request.data.get('text') or '').strip()
        if word_count(text) < MIN_WORDS_FLASHCARDS:
            return Response({'detail': _('That text is too short to study from. Paste at least '
                                         '%(n)s words.') % {'n': MIN_WORDS_FLASHCARDS}}, status=400)
        title = (request.data.get('title') or '').strip() or default_title(text)
        source = Source.objects.create(notebook=notebook, title=title[:255], file_type='text',
                                       extracted_text=text)
        finish_text_source(source)
        notebook.save(update_fields=['updated_at'])
        return Response(SourceSerializer(source, context={'request': request}).data, status=201)

    @action(detail=True, methods=['post'])
    def add_url(self, request, pk=None):
        """A source from a web page. The fetch is guarded against private
        addresses and bounded in time and size (see services/fetch_page)."""
        notebook = self.get_object()
        url = (request.data.get('url') or '').strip()
        if not url:
            return Response({'detail': _('Paste a link first.')}, status=400)
        try:
            page_title, text = fetch_page(url)
        except PageFetchError as exc:
            return Response({'detail': str(exc)}, status=400)
        text = normalise_text(text)
        if word_count(text) < MIN_WORDS_FLASHCARDS:
            return Response({'detail': _('That page has too little text to study from.')}, status=400)
        title = (request.data.get('title') or '').strip() or page_title or default_title(text)
        source = Source.objects.create(notebook=notebook, title=title[:255], file_type='url',
                                       original_filename=url[:255], extracted_text=text)
        finish_text_source(source)
        notebook.save(update_fields=['updated_at'])
        return Response(SourceSerializer(source, context={'request': request}).data, status=201)

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_pdf(self, request, pk=None):
        """Upload a source file (PDF, DOCX, or PPTX) to this notebook."""
        notebook = self.get_object()
        uploaded = request.FILES.get('file')

        if not uploaded:
            return Response({'detail': _('No file provided.')}, status=400)

        file_type = file_type_from_filename(uploaded.name)
        if not file_type:
            return Response(
                {'detail': _('Unsupported file type. Supported: %(formats)s.') % {'formats': SUPPORTED_FORMATS}},
                status=400,
            )

        max_bytes = getattr(settings, 'MAX_PDF_UPLOAD_MB', 10) * 1024 * 1024
        if uploaded.size > max_bytes:
            return Response(
                {'detail': _('File too large. Max size is %(mb)s MB.') % {'mb': settings.MAX_PDF_UPLOAD_MB}},
                status=400,
            )

        title = request.data.get('title') or title_from_filename(uploaded.name)
        source = Source.objects.create(
            notebook=notebook,
            title=title,
            file=uploaded,
            file_type=file_type,
            original_filename=uploaded.name,
            status='processing',
        )

        process_source(source)
        notebook.save(update_fields=['updated_at'])

        return Response(SourceSerializer(source, context={'request': request}).data, status=201)

    @action(detail=True, methods=['post'], throttle_classes=[GenerationRateThrottle])
    def generate_flashcards(self, request, pk=None):
        """Generate flashcards from one or more sources in this notebook."""
        notebook = self.get_object()
        source_ids = request.data.get('source_ids') or []
        if isinstance(source_ids, (int, str)):
            source_ids = [source_ids]
        source_ids = [int(i) for i in source_ids]
        if not source_ids:
            return Response({'detail': _('Choose at least one source.')}, status=400)

        sources = list(
            Source.objects.filter(notebook=notebook, id__in=source_ids).order_by('id')
        )
        if len(sources) != len(source_ids):
            return Response({'detail': _('One or more sources are not in this notebook.')}, status=400)

        count = int(request.data.get('count', 10))
        meta = {}
        try:
            cards = generate_flashcards_for_sources(sources, request.user, count=count, meta=meta)
        except GeminiNotConfiguredError as exc:
            return Response({'detail': str(exc)}, status=503)
        except (GeminiGenerationError, ValueError) as exc:
            return Response({'detail': _user_error(exc)}, status=400)

        serializer = FlashcardSerializer(cards, many=True, context={'request': request})
        return Response({
            'message': f'Created {len(cards)} flashcards',
            'count': len(cards),
            'source_ids': source_ids,
            'generated_by': meta.get('provider'),
            'fallback_reason': meta.get('reason'),
            'flashcards': serializer.data,
        }, status=201)

    @action(detail=True, methods=['get'])
    def material_counts(self, request, pk=None):
        """What this exact source selection already has: cards, and a quiz.

        Generating replaces this selection's deck, so the page has to be able
        to warn that a press discards cards the learner may have been part-way
        through. Keyed on the same combined tag that generation writes and
        retires against, so this is exactly the number the next press replaces.

        `quiz_id` is here so the workspace can offer a "study" link without
        downloading every flashcard and every quiz the user owns just to test
        whether one of them matches — which is what it did before, and which
        grew with the whole collection rather than with this selection.
        Counts and one id: no card or question text is loaded.
        """
        self.get_object()  # 404s unless the notebook belongs to this user
        raw = request.query_params.get('source_ids', '')
        source_ids = sorted({int(i) for i in raw.split(',') if i.strip().isdigit()})
        if not source_ids:
            return Response({'flashcards': 0, 'quiz_id': None})

        # The deck for this exact selection — every selected source and no
        # other — because that is the set a generate press retires, and the
        # number shown must be the number that press costs. Active cards only:
        # an archived original is already retired.
        deck = items_with_exact_sources(
            Flashcard.sources.through.objects
            .filter(flashcard__user=request.user, flashcard__archived=False)
            .values_list('flashcard_id', 'source_id'),
            source_ids)
        quizzes = items_with_exact_sources(
            Quiz.sources.through.objects
            .filter(quiz__user=request.user, quiz__is_published=True)
            .values_list('quiz_id', 'source_id'),
            source_ids)
        quiz_id = (Quiz.objects.filter(id__in=quizzes).order_by('-created_at')
                   .values_list('id', flat=True).first())
        return Response({'flashcards': len(deck), 'quiz_id': quiz_id})

    @action(detail=True, methods=['post'], throttle_classes=[GenerationRateThrottle])
    def generate_quiz(self, request, pk=None):
        """Generate a quiz from one or more sources in this notebook."""
        notebook = self.get_object()
        source_ids = request.data.get('source_ids') or []
        if isinstance(source_ids, (int, str)):
            source_ids = [source_ids]
        source_ids = [int(i) for i in source_ids]
        if not source_ids:
            return Response({'detail': _('Choose at least one source.')}, status=400)

        sources = list(
            Source.objects.filter(notebook=notebook, id__in=source_ids).order_by('id')
        )
        if len(sources) != len(source_ids):
            return Response({'detail': _('One or more sources are not in this notebook.')}, status=400)

        question_count = int(request.data.get('question_count', 8))
        meta = {}
        try:
            quiz = generate_quiz_for_sources(
                sources, request.user, question_count=question_count, meta=meta)
        except GeminiNotConfiguredError as exc:
            return Response({'detail': str(exc)}, status=503)
        except (GeminiGenerationError, ValueError) as exc:
            return Response({'detail': _user_error(exc)}, status=400)

        serializer = QuizSerializer(quiz, context={'request': request})
        return Response({
            'message': f'Created quiz with {quiz.questions.count()} questions',
            'source_ids': source_ids,
            'generated_by': meta.get('provider'),
            'fallback_reason': meta.get('reason'),
            'quiz': serializer.data,
        }, status=201)


class SourceViewSet(
    mixins.DestroyModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SourceSerializer

    def get_queryset(self):
        return Source.objects.filter(notebook__user=self.request.user)

    def perform_destroy(self, instance):
        if instance.file:
            instance.file.delete(save=False)
        instance.delete()

    @action(detail=True, methods=['post'], throttle_classes=[GenerationRateThrottle])
    def generate_flashcards(self, request, pk=None):
        source = self.get_object()
        count = int(request.data.get('count', 10))

        try:
            cards = generate_flashcards_for_source(source, request.user, count=count)
        except GeminiNotConfiguredError as exc:
            return Response({'detail': str(exc)}, status=503)
        except (GeminiGenerationError, ValueError) as exc:
            return Response({'detail': _user_error(exc)}, status=400)

        serializer = FlashcardSerializer(cards, many=True, context={'request': request})
        return Response({
            'message': f'Created {len(cards)} flashcards',
            'count': len(cards),
            'source_id': source.id,
            'flashcards': serializer.data,
        }, status=201)

    @action(detail=True, methods=['post'], throttle_classes=[GenerationRateThrottle])
    def generate_quiz(self, request, pk=None):
        source = self.get_object()
        question_count = int(request.data.get('question_count', 8))

        try:
            quiz = generate_quiz_for_source(source, request.user, question_count=question_count)
        except GeminiNotConfiguredError as exc:
            return Response({'detail': str(exc)}, status=503)
        except (GeminiGenerationError, ValueError) as exc:
            return Response({'detail': _user_error(exc)}, status=400)

        serializer = QuizSerializer(quiz, context={'request': request})
        return Response({
            'message': f'Created quiz with {quiz.questions.count()} questions',
            'source_id': source.id,
            'quiz': serializer.data,
        }, status=201)
