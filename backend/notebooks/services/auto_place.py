"""A file dropped on the notebooks page, placed in the notebook for its subject.

The text is compared with the documents in the student's own notebooks
(ml_pipeline.subject_match, no model call). Close enough to one, it joins
it. Otherwise the model names the subject and a notebook of that name is
used, or made. The name is asked for in the same request as the summary
every upload already gets, so placing a file costs nothing extra.

Only notebooks the student owns are candidates. A notebook someone shared
with them is visible to others, and a file must not reach those people
because its words resembled their lecture.
"""
import logging
import os
import tempfile

from django.db import transaction

from ml_pipeline.language import detect_language, language_name
from ml_pipeline.subject_match import best_notebook

from ..models import Notebook, Source
from .ai_provider import get_ai_provider
from .document_extract import extract_text_from_document, title_from_filename
from .textnorm import clean_summary, normalise_text

logger = logging.getLogger(__name__)

MAX_SUBJECT_CHARS = 60


class NothingToRead(ValueError):
    """The file held no extractable text."""


def place_upload(user, uploaded, file_type: str, ui_language: str = 'en'):
    """Create the Source in the right notebook. Returns (source, notebook, created)."""
    text, page_count = _read(uploaded, file_type)
    title = title_from_filename(uploaded.name)

    own = {nb.id: nb for nb in Notebook.objects.filter(user=user)}
    documents = {nb_id: [] for nb_id in own}
    for nb_id, doc in (Source.objects.filter(notebook__in=own.values(), status='ready')
                       .values_list('notebook_id', 'extracted_text')):
        documents[nb_id].append(doc)

    match = best_notebook(text, documents)
    created = False
    if match is not None:
        notebook = own[match]
        summary = _summary(text, title)
    else:
        subject, summary = _subject_and_summary(text, title, ui_language)
        # Without a model, the file's own name: "Westphalia_treaty" reads as
        # "Westphalia treaty".
        notebook, created = _notebook_named(user, subject or title.replace('_', ' '))

    with transaction.atomic():
        source = Source.objects.create(
            notebook=notebook, title=title, file=uploaded, file_type=file_type,
            original_filename=uploaded.name, status='ready', extracted_text=text,
            page_count=page_count, gemini_summary=summary)
        notebook.save(update_fields=['updated_at'])
    return source, notebook, created


def _read(uploaded, file_type: str) -> tuple[str, int]:
    # Extraction reads a path; the upload may still be in memory.
    suffix = os.path.splitext(uploaded.name)[1]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        for chunk in uploaded.chunks():
            tmp.write(chunk)
        path = tmp.name
    try:
        text, page_count = extract_text_from_document(path, file_type)
    finally:
        os.unlink(path)
        uploaded.seek(0)
    text = normalise_text(text)
    if not text.strip():
        raise NothingToRead('No text could be extracted from this file.')
    return text, page_count


def _summary(text: str, title: str) -> str:
    try:
        return clean_summary(get_ai_provider().summarize(text, title))
    except Exception as exc:  # noqa: BLE001 — a missing summary never blocks an upload
        logger.info('Upload summary unavailable: %s', exc)
        return ''


def _subject_and_summary(text: str, title: str, ui_language: str) -> tuple[str, str]:
    """The subject's name (in the student's language) and the overview (in
    the document's), from one request. Either may come back empty."""
    doc_language = language_name(detect_language(text))
    prompt = f"""A student uploaded a document titled "{title}".
1. Name the school subject or course it belongs to, as a notebook title: 2 to 5 words, in
   {language_name(ui_language)}, general enough that other lectures of the same course fit under it
   (for example "Organic chemistry", not the title of this one lecture). No quotes, no trailing period.
2. Write a clear 3–5 sentence overview of its main topics, in {doc_language}.

Document text:
{text[:30000]}

Return ONLY valid JSON: {{"subject": "...", "summary": "..."}}"""
    try:
        data = get_ai_provider().generate_json(prompt)
    except Exception as exc:  # noqa: BLE001 — named from the file instead
        logger.info('Subject naming unavailable: %s', exc)
        return '', ''
    if not isinstance(data, dict):
        return '', ''
    subject = str(data.get('subject') or '').strip().strip('."\'')[:MAX_SUBJECT_CHARS]
    return subject, clean_summary(str(data.get('summary') or '').strip())


def _notebook_named(user, name: str) -> tuple[Notebook, bool]:
    """The student's notebook with this name, or a new one. A subject named
    the same as one they have goes there, not into a second copy."""
    name = ' '.join(name.split())[:255] or 'Untitled'
    for nb in Notebook.objects.filter(user=user):
        if nb.title.casefold().strip() == name.casefold():
            return nb, False
    return Notebook.objects.create(user=user, title=name), True
