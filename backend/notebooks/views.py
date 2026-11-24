from rest_framework import mixins, viewsets, permissions, status
from rest_framework.exceptions import PermissionDenied
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
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from asgiref.sync import sync_to_async
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404

from .models import Notebook, NotebookMember, Source
from .services.membership import can_manage, notebooks_for
from .serializers import (
    NotebookSerializer,
    NotebookCreateSerializer,
    SourceSerializer,
)
from .services.document_extract import extract_text_from_document, file_type_from_filename, title_from_filename
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
        # Own notebooks and shared ones; writes are narrowed per action below.
        return notebooks_for(self.request.user).prefetch_related(
            Prefetch('sources', queryset=Source.objects.defer('extracted_text'))
        )

    def retrieve(self, request, *args, **kwargs):
        from .services.ingest import fail_stalled
        fail_stalled(self.get_object())
        return super().retrieve(request, *args, **kwargs)

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return NotebookCreateSerializer
        return NotebookSerializer

    def perform_update(self, serializer):
        # Renaming is the owner's; a member adding documents is not renaming.
        if not can_manage(serializer.instance, self.request.user):
            raise PermissionDenied(_('Only the notebook owner can change it.'))
        serializer.save()

    def perform_destroy(self, instance):
        if not can_manage(instance, self.request.user):
            raise PermissionDenied(_('Only the notebook owner can delete it.'))
        instance.delete()

    def perform_create(self, serializer):
        # Ownership is the model's doing (see the post_save in models.py), so
        # every path that makes a notebook produces a notebook with an owner.
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
            page = fetch_page(url)
        except PageFetchError as exc:
            return Response({'detail': str(exc)}, status=400)

        if page.kind == 'pdf':
            # A PDF link is an upload the student did not have to do by hand:
            # keep the file, run the same extraction, name it from the URL.
            from django.core.files.base import ContentFile
            from urllib.parse import urlparse
            import os
            name = os.path.basename(urlparse(url).path) or 'document.pdf'
            if not name.lower().endswith('.pdf'):
                name += '.pdf'
            title = (request.data.get('title') or '').strip() or title_from_filename(name)
            source = Source.objects.create(notebook=notebook, title=title[:255], file_type='pdf',
                                           original_filename=url[:255])
            source.file.save(name, ContentFile(page.pdf), save=True)
            text, page_count = extract_text_from_document(source.file.path, 'pdf')
            text = normalise_text(text)
            if word_count(text) < MIN_WORDS_FLASHCARDS:
                source.delete()
                return Response({'detail': _('No readable text was found in that PDF. It may be '
                                             'scanned images only.')}, status=400)
            source.extracted_text = text
            source.page_count = page_count
            finish_text_source(source)
            notebook.save(update_fields=['updated_at'])
            return Response(SourceSerializer(source, context={'request': request}).data, status=201)

        text = normalise_text(page.text)
        if word_count(text) < MIN_WORDS_FLASHCARDS:
            return Response({'detail': _('That page has too little text to study from.')}, status=400)
        title = (request.data.get('title') or '').strip() or page.title or default_title(text)
        source = Source.objects.create(notebook=notebook, title=title[:255], file_type='url',
                                       original_filename=url[:255], extracted_text=text)
        finish_text_source(source)
        notebook.save(update_fields=['updated_at'])
        return Response(SourceSerializer(source, context={'request': request}).data, status=201)

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def auto_upload(self, request):
        """Upload a file from the notebooks page; it is placed in the notebook
        for its subject, which is made if the student has none (auto_place)."""
        from .services.auto_place import NothingToRead, place_upload

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
        try:
            source, notebook, created = place_upload(
                request.user, uploaded, file_type, getattr(request, 'LANGUAGE_CODE', 'vi') or 'vi')
        except NothingToRead:
            return Response({'detail': _('No text could be extracted from this file.')}, status=400)
        return Response({
            'source': SourceSerializer(source, context={'request': request}).data,
            'notebook': {'id': notebook.id, 'title': notebook.title},
            'created_notebook': created,
        }, status=201)

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

        from .services.ingest import needs_ocr, process_in_background
        if file_type == 'pdf' and needs_ocr(source.file.path):
            # A scanned PDF: minutes of OCR. The page shows it as processing
            # and checks back until it is ready.
            process_in_background(source)
        else:
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

    @action(detail=True, methods=['post'])
    def invite(self, request, pk=None):
        """Invite someone by email. The response always carries the link, so
        an inviter can pass it on even when mail is not configured."""
        from .services.invites import create_invite, invite_url, send_invite_email

        notebook = self.get_object()
        if not can_manage(notebook, request.user):
            return Response({'detail': _('Only the notebook owner can invite people.')}, status=403)
        email = (str(request.data.get('email') or '')).strip()
        if '@' not in email or len(email) > 254:
            return Response({'detail': _('Enter an email address.')}, status=400)
        if email.lower() == (request.user.email or '').lower():
            return Response({'detail': _('That is your own address.')}, status=400)

        invite = create_invite(notebook, request.user, email)
        sent = send_invite_email(invite, request.user.first_name or request.user.email or 'A student',
                                 _profile_language(request.user))
        return Response({'email': invite.email, 'token': invite.token,
                         'url': invite_url(invite.token), 'emailed': sent}, status=201)

    @action(detail=True, methods=['get'])
    def members(self, request, pk=None):
        """Who is in this notebook, and how each of them is doing in it.

        The record is per member and scoped to this notebook: how many
        reviews they have graded here and their mastery. It is the point of
        studying together, and it says nothing about anyone's other work.
        """
        from .services.group import member_records

        notebook = self.get_object()
        return Response({'members': member_records(notebook, request.user)})

    @action(detail=True, methods=['get'], url_path='map')
    def knowledge_map(self, request, pk=None):
        """The caller's own mastery of this notebook's concepts, for each
        document's key points list."""
        from .services.knowledge_map import build_map
        return Response(build_map(request.user, self.get_object()))

    @action(detail=True, methods=['delete'], url_path=r'members/(?P<member_id>\d+)')
    def remove_member(self, request, pk=None, member_id=None):
        """Leave the notebook, or (as owner) remove someone from it."""
        notebook = self.get_object()
        member_id = int(member_id)
        leaving_self = member_id == request.user.id
        if not leaving_self and not can_manage(notebook, request.user):
            return Response({'detail': _('Only the notebook owner can remove people.')}, status=403)
        if member_id == notebook.user_id:
            return Response({'detail': _('The owner cannot leave their own notebook.')}, status=400)
        NotebookMember.objects.filter(notebook=notebook, user_id=member_id).delete()
        return Response(status=204)

    @action(detail=True, methods=['get'])
    def export(self, request, pk=None):
        """The notebook's live cards or published questions as a CSV download
        — the student's data in a form that opens in Excel and imports into
        Anki. Live only: an archived card or a retired quiz is history."""
        from django.http import HttpResponse
        from django.utils.text import slugify
        from flashcards.models import Flashcard
        from quizzes.models import Question
        from .services.export_csv import flashcards_csv, questions_csv

        notebook = self.get_object()
        kind = request.query_params.get('kind')
        if kind == 'flashcards':
            cards = list(Flashcard.objects
                         .filter(user=request.user, archived=False, sources__notebook=notebook)
                         .distinct().order_by('id').prefetch_related('sources'))
            for c in cards:
                c.source_titles = [s.title for s in c.sources.all()]
            body = flashcards_csv(cards)
        elif kind == 'questions':
            questions = list(Question.objects
                             .filter(quiz__user=request.user, quiz__is_published=True,
                                     quiz__sources__notebook=notebook)
                             .distinct().order_by('quiz_id', 'order', 'id').select_related('source'))
            for q in questions:
                q.source_title = q.source.title if q.source else ''
            body = questions_csv(questions)
        else:
            return Response({'detail': _('kind must be flashcards or questions.')}, status=400)

        filename = f"{slugify(notebook.title) or 'notebook'}-{kind}.csv"
        res = HttpResponse(body, content_type='text/csv; charset=utf-8')
        res['Content-Disposition'] = f'attachment; filename="{filename}"'
        return res

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
            return Response({'flashcards': 0, 'to_do': 0, 'quiz_id': None})

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
        # Cards not yet remembered: what "Ôn thẻ" still has to offer.
        from study_sessions.forgotten import remembered_ids
        to_do = len(deck) - len(remembered_ids(request.user, deck))
        return Response({'flashcards': len(deck), 'to_do': to_do, 'quiz_id': quiz_id})

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


class InviteAcceptView(APIView):
    """Redeem an invitation link."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from .services.invites import InviteError, accept_invite

        try:
            invite = accept_invite(str(request.data.get('token') or ''), request.user)
        except LookupError:
            return Response({'detail': _('This invitation link is not valid.')}, status=404)
        except InviteError as exc:
            return Response({'detail': str(exc)}, status=400)
        nb = invite.notebook
        return Response({'notebook': {'id': nb.id, 'title': nb.title}})


class TranslateView(APIView):
    """Checks a request for a document's texts in the page language and plans
    it (services/translate.py): what is kept already, what the model has to
    do. The plan rides on the response; translate_view carries it out."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from .services.translate import LANGUAGES, MAX_CHARS, MAX_TEXTS, plan_texts

        texts, target = request.data.get('texts'), request.data.get('to')
        # The question each text answers, for short answers; None for the rest.
        contexts = request.data.get('contexts')
        if (target not in LANGUAGES or not isinstance(texts, list) or len(texts) > MAX_TEXTS
                or not all(isinstance(t, str) and len(t) <= MAX_CHARS for t in texts)
                or (contexts is not None and (not isinstance(contexts, list) or len(contexts) != len(texts)
                    or not all(c is None or (isinstance(c, str) and len(c) <= MAX_CHARS) for c in contexts)))):
            return Response({'detail': _('Send up to %(count)s texts of up to %(chars)s characters each, '
                                         'and the language to translate to (vi or en).')
                             % {'count': MAX_TEXTS, 'chars': MAX_CHARS}}, status=400)
        response = Response()
        response.plan = plan_texts(texts, target, contexts)
        return response


@csrf_exempt  # token-authenticated, like every DRF view here
async def translate_view(request):
    """POST /notebooks/translate/. Under ASGI Django runs every synchronous
    view on one shared thread, one request at a time, and a translation takes
    seconds: the rest of the API (generating cards, a quiz) queued behind it.
    So only the checks and the database run on that thread; the model runs
    on a thread of its own."""
    from .services.translate import finish, run

    checked = await sync_to_async(_checked)(request)
    plan = getattr(checked, 'plan', None)
    if plan is None:
        return checked                           # refused: not signed in, or a bad request
    done = await sync_to_async(run, thread_sensitive=False)(plan)
    translations, translated = await sync_to_async(finish)(plan, done)
    return JsonResponse({'translations': translations, 'translated': translated})


def _checked(request):
    response = TranslateView.as_view()(request)
    response.render()
    return response


class ChatMessageView(APIView):
    """Deleting one line of a group thread: its author only."""
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, message_id):
        from .models import GroupMessage
        from .services.chat import in_group, room_for

        message = GroupMessage.objects.filter(id=message_id).select_related('group').first()
        if message is None or not in_group(message.group, request.user):
            return Response({'detail': _('Message not found.')}, status=404)
        if message.user_id != request.user.id:
            return Response({'detail': _('Only the person who wrote it can delete a message.')}, status=403)
        group_id, deleted_id = message.group_id, message.id
        message.delete()
        from .realtime import emit_to_room
        emit_to_room(room_for(group_id), 'message:deleted', {'group': group_id, 'id': deleted_id})
        return Response(status=204)


class ChatGroupsView(APIView):
    """The groups you are in, and making a new one."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from .services.chat import create_group

        members = request.data.get('members') or []
        if not isinstance(members, list) or not all(isinstance(i, int) for i in members):
            return Response({'detail': _('members must be a list of user ids.')}, status=400)
        try:
            group = create_group(request.user, str(request.data.get('name') or ''), members)
        except PermissionError:
            return Response({'detail': _('You can only add people you share a notebook with.')}, status=400)
        except ValueError:
            return Response({'detail': _('Give the group a name.')}, status=400)
        return Response({'id': group.id, 'name': group.name}, status=201)


class ChatGroupMessagesView(APIView):
    """One group's thread: read it, or add to it."""
    permission_classes = [permissions.IsAuthenticated]

    def _group_or_none(self, request, group_id):
        from .models import ChatGroup
        from .services.chat import in_group

        group = ChatGroup.objects.filter(id=group_id).first()
        # A group you are not in is reported missing, not forbidden: its
        # existence is nobody else's business.
        return group if group and in_group(group, request.user) else None

    def get(self, request, group_id):
        from .services.chat import HISTORY_LIMIT, history

        group = self._group_or_none(request, group_id)
        if group is None:
            return Response({'detail': _('Group not found.')}, status=404)
        before = request.query_params.get('before')
        before = int(before) if (before or '').isdigit() else None
        return Response({'messages': history(group, request.user, HISTORY_LIMIT, before)})

    def post(self, request, group_id):
        from .services.chat import message_payload, post_message, room_for

        group = self._group_or_none(request, group_id)
        if group is None:
            return Response({'detail': _('Group not found.')}, status=404)
        try:
            message = post_message(group, request.user, str(request.data.get('body') or ''))
        except PermissionError:
            return Response({'detail': _('You are not in this group.')}, status=403)
        except ValueError:
            return Response({'detail': _('A message must have text, and stay under 2000 characters.')},
                            status=400)
        payload = message_payload(message)
        from .realtime import emit_to_room
        emit_to_room(room_for(group.id), 'message:new', payload)
        return Response(message_payload(message, request.user), status=201)


class ChatGroupMembersView(APIView):
    """Adding someone to a group, and leaving it."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, group_id):
        from django.contrib.auth.models import User
        from .models import ChatGroup
        from .services.chat import add_member

        group = ChatGroup.objects.filter(id=group_id).first()
        person = User.objects.filter(id=request.data.get('user_id')).first()
        if group is None or person is None:
            return Response({'detail': _('Group not found.')}, status=404)
        try:
            add_member(group, request.user, person)
        except PermissionError:
            return Response({'detail': _('You can only add people you share a notebook with.')}, status=403)
        return Response({'user_id': person.id}, status=201)

    def delete(self, request, group_id, user_id):
        from .models import ChatGroup, ChatGroupMember
        from .services.chat import in_group

        group = ChatGroup.objects.filter(id=group_id).first()
        if group is None or not in_group(group, request.user):
            return Response({'detail': _('Group not found.')}, status=404)
        if user_id != request.user.id:
            return Response({'detail': _('You can only leave a group yourself.')}, status=403)
        ChatGroupMember.objects.filter(group=group, user_id=user_id).delete()
        return Response(status=204)


class ChatOverviewView(APIView):
    """What the chat launcher lists: your notebooks, and the people in them."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from .services.chat import chat_overview
        return Response(chat_overview(request.user))


class DirectThreadView(APIView):
    """One private thread: read it, or add to it."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, user_id):
        from django.contrib.auth.models import User
        from .services.chat import HISTORY_LIMIT, direct_history

        other = User.objects.filter(id=user_id).first()
        if other is None:
            return Response({'detail': _('Person not found.')}, status=404)
        before = request.query_params.get('before')
        before = int(before) if (before or '').isdigit() else None
        return Response({'messages': direct_history(request.user, other, HISTORY_LIMIT, before)})

    def post(self, request, user_id):
        from django.contrib.auth.models import User
        from .services.chat import direct_payload, send_direct, user_room

        other = User.objects.filter(id=user_id).first()
        if other is None:
            return Response({'detail': _('Person not found.')}, status=404)
        if other.id == request.user.id:
            # Not a permission problem, just not a thing: 400, not 403.
            return Response({'detail': _('You cannot message yourself.')}, status=400)
        try:
            message = send_direct(request.user, other, str(request.data.get('body') or ''))
        except PermissionError:
            return Response({'detail': _('You can only message people you share a notebook with.')},
                            status=403)
        except ValueError:
            return Response({'detail': _('A message must have text, and stay under 2000 characters.')},
                            status=400)
        # Delivered to both sides: each client sees the thread from its own
        # end, so the payload names the other person rather than the sender.
        from .realtime import emit_to_room
        emit_to_room(user_room(other.id), 'direct:new', direct_payload(message, other))
        emit_to_room(user_room(request.user.id), 'direct:new', direct_payload(message, request.user))
        return Response(direct_payload(message, request.user), status=201)


class SourceViewSet(
    mixins.DestroyModelMixin,
    viewsets.ReadOnlyModelViewSet,
):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SourceSerializer

    def get_queryset(self):
        return Source.objects.filter(notebook__in=notebooks_for(self.request.user))

    def perform_destroy(self, instance):
        if instance.file:
            instance.file.delete(save=False)
        instance.delete()

    @action(detail=True, methods=['post'], throttle_classes=[GenerationRateThrottle])
    def read(self, request, pk=None):
        """Read an older document's main ideas now (once; they are kept)."""
        from .services.key_points import ensure_key_points
        source = self.get_object()
        if not ensure_key_points(source):
            return Response({'detail': _('The main ideas could not be read just now. Try again in a few minutes.')},
                            status=503)
        source.refresh_from_db()
        return Response(SourceSerializer(source, context={'request': request}).data)

    @action(detail=True, methods=['post'])
    def move(self, request, pk=None):
        """Move a document to another of the student's own notebooks, or to a
        new one ({notebook_id} or {new_notebook_title}). Cards made from this
        document alone go with it.

        `drop_empty_notebook` removes the notebook it leaves if that is now
        empty: the page sends it only for a notebook made for this very file
        a moment ago, so a notebook the student made is never deleted here.
        """
        from flashcards.models import Flashcard
        from .services.auto_place import _notebook_named

        source = self.get_object()
        old = source.notebook
        if old.user_id != request.user.id:
            return Response({'detail': _('Only the notebook owner can move its documents.')}, status=403)
        new_title = str(request.data.get('new_notebook_title') or '').strip()
        if new_title:
            target, _created = _notebook_named(request.user, new_title)
        else:
            target = Notebook.objects.filter(id=request.data.get('notebook_id'), user=request.user).first()
            if target is None:
                return Response({'detail': _('Choose one of your own notebooks.')}, status=400)
        if target.id == old.id:
            return Response({'notebook': {'id': target.id, 'title': target.title}})

        with transaction.atomic():
            source.notebook = target
            source.save(update_fields=['notebook'])
            only_this = [c.id for c in Flashcard.objects.filter(notebook=old, sources=source)
                         if set(c.sources.values_list('id', flat=True)) == {source.id}]
            Flashcard.objects.filter(id__in=only_this).update(notebook=target)
            if (request.data.get('drop_empty_notebook') and not old.sources.exists()
                    and not Flashcard.objects.filter(notebook=old).exists()
                    and old.members.exclude(user=request.user).count() == 0):
                old.delete()
        return Response({'notebook': {'id': target.id, 'title': target.title}})

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


def _profile_language(user) -> str:
    """The invitee gets the inviter's language: it is the only clue we have
    about which language the pair studies in."""
    profile = getattr(user, 'profile', None)
    return getattr(profile, 'preferred_language', 'vi') or 'vi'


