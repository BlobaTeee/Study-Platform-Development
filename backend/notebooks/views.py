from rest_framework import mixins, viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.conf import settings

from .models import Notebook, Source
from .serializers import (
    NotebookSerializer,
    NotebookCreateSerializer,
    SourceSerializer,
)
from .services.document_extract import file_type_from_filename, title_from_filename
from .services.ingest import process_source
from .services.gemini_client import GeminiNotConfiguredError, GeminiGenerationError
from .services.generate import (
    combined_source_tag,
    generate_flashcards_for_sources,
    generate_quiz_for_sources,
    generate_flashcards_for_source,
    generate_quiz_for_source,
)
from flashcards.models import Flashcard
from flashcards.serializers import FlashcardSerializer
from quizzes.serializers import QuizSerializer

SUPPORTED_FORMATS = 'PDF, Word (.docx), and PowerPoint (.pptx)'


class NotebookViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        return Notebook.objects.filter(user=self.request.user).prefetch_related('sources')

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return NotebookCreateSerializer
        return NotebookSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_pdf(self, request, pk=None):
        """Upload a source file (PDF, DOCX, or PPTX) to this notebook."""
        notebook = self.get_object()
        uploaded = request.FILES.get('file')

        if not uploaded:
            return Response({'detail': 'No file provided. Use form field "file".'}, status=400)

        file_type = file_type_from_filename(uploaded.name)
        if not file_type:
            return Response(
                {'detail': f'Unsupported file type. Supported: {SUPPORTED_FORMATS}.'},
                status=400,
            )

        max_bytes = getattr(settings, 'MAX_PDF_UPLOAD_MB', 10) * 1024 * 1024
        if uploaded.size > max_bytes:
            return Response(
                {'detail': f'File too large. Max size is {settings.MAX_PDF_UPLOAD_MB} MB.'},
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

    @action(detail=True, methods=['post'])
    def generate_flashcards(self, request, pk=None):
        """Generate flashcards from one or more sources in this notebook."""
        notebook = self.get_object()
        source_ids = request.data.get('source_ids') or []
        if isinstance(source_ids, (int, str)):
            source_ids = [source_ids]
        source_ids = [int(i) for i in source_ids]
        if not source_ids:
            return Response({'detail': 'Provide source_ids (array of source IDs).'}, status=400)

        sources = list(
            Source.objects.filter(notebook=notebook, id__in=source_ids).order_by('id')
        )
        if len(sources) != len(source_ids):
            return Response({'detail': 'One or more sources not found in this notebook.'}, status=400)

        count = int(request.data.get('count', 10))
        meta = {}
        try:
            cards = generate_flashcards_for_sources(sources, request.user, count=count, meta=meta)
        except GeminiNotConfiguredError as exc:
            return Response({'detail': str(exc)}, status=503)
        except (GeminiGenerationError, ValueError) as exc:
            return Response({'detail': str(exc)}, status=400)

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
        """How many flashcards this exact source selection already has.

        Generating replaces this selection's deck, so the page has to be able
        to warn that a press discards cards the learner may have been part-way
        through. Keyed on the same combined tag that generation writes and
        retires against, so this is exactly the number the next press replaces.
        Counts only — no card text is loaded.
        """
        self.get_object()  # 404s unless the notebook belongs to this user
        raw = request.query_params.get('source_ids', '')
        source_ids = sorted({int(i) for i in raw.split(',') if i.strip().isdigit()})
        if not source_ids:
            return Response({'flashcards': 0})
        return Response({
            # Active cards only: an archived original is already retired, so
            # counting it would overstate what a regeneration costs.
            'flashcards': Flashcard.objects.filter(
                user=request.user, tags=combined_source_tag(source_ids), archived=False
            ).count(),
        })

    @action(detail=True, methods=['post'])
    def generate_quiz(self, request, pk=None):
        """Generate a quiz from one or more sources in this notebook."""
        notebook = self.get_object()
        source_ids = request.data.get('source_ids') or []
        if isinstance(source_ids, (int, str)):
            source_ids = [source_ids]
        source_ids = [int(i) for i in source_ids]
        if not source_ids:
            return Response({'detail': 'Provide source_ids (array of source IDs).'}, status=400)

        sources = list(
            Source.objects.filter(notebook=notebook, id__in=source_ids).order_by('id')
        )
        if len(sources) != len(source_ids):
            return Response({'detail': 'One or more sources not found in this notebook.'}, status=400)

        question_count = int(request.data.get('question_count', 8))
        meta = {}
        try:
            quiz = generate_quiz_for_sources(
                sources, request.user, question_count=question_count, meta=meta)
        except GeminiNotConfiguredError as exc:
            return Response({'detail': str(exc)}, status=503)
        except (GeminiGenerationError, ValueError) as exc:
            return Response({'detail': str(exc)}, status=400)

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

    @action(detail=True, methods=['post'])
    def generate_flashcards(self, request, pk=None):
        source = self.get_object()
        count = int(request.data.get('count', 10))

        try:
            cards = generate_flashcards_for_source(source, request.user, count=count)
        except GeminiNotConfiguredError as exc:
            return Response({'detail': str(exc)}, status=503)
        except (GeminiGenerationError, ValueError) as exc:
            return Response({'detail': str(exc)}, status=400)

        serializer = FlashcardSerializer(cards, many=True, context={'request': request})
        return Response({
            'message': f'Created {len(cards)} flashcards',
            'count': len(cards),
            'source_id': source.id,
            'flashcards': serializer.data,
        }, status=201)

    @action(detail=True, methods=['post'])
    def generate_quiz(self, request, pk=None):
        source = self.get_object()
        question_count = int(request.data.get('question_count', 8))

        try:
            quiz = generate_quiz_for_source(source, request.user, question_count=question_count)
        except GeminiNotConfiguredError as exc:
            return Response({'detail': str(exc)}, status=503)
        except (GeminiGenerationError, ValueError) as exc:
            return Response({'detail': str(exc)}, status=400)

        serializer = QuizSerializer(quiz, context={'request': request})
        return Response({
            'message': f'Created quiz with {quiz.questions.count()} questions',
            'source_id': source.id,
            'quiz': serializer.data,
        }, status=201)
