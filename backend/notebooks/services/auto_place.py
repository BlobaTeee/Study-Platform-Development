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

from ml_pipeline.subject_match import best_notebook

from ..models import Notebook, Source
from .document_extract import extract_text_from_document, title_from_filename
from .textnorm import normalise_text
from .key_points import read_document

logger = logging.getLogger(__name__)

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
    # One request either way: the overview and main ideas, plus the subject's
    # name when the file needs a notebook of its own.
    reading = read_document(text, title, subject_language=None if match is not None else ui_language)
    summary, subject = reading['summary'], reading['subject']
    if match is not None:
        notebook = own[match]
    else:
        # Without a model, the file's own name: "Westphalia_treaty" reads as
        # "Westphalia treaty".
        notebook, created = _notebook_named(user, subject or title.replace('_', ' '))

    with transaction.atomic():
        source = Source.objects.create(
            notebook=notebook, title=title, file=uploaded, file_type=file_type,
            original_filename=uploaded.name, status='ready', extracted_text=text,
            page_count=page_count, gemini_summary=summary, key_points=reading['key_points'])
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


def _notebook_named(user, name: str) -> tuple[Notebook, bool]:
    """The student's notebook with this name, or a new one. A subject named
    the same as one they have goes there, not into a second copy."""
    name = ' '.join(name.split())[:255] or 'Untitled'
    for nb in Notebook.objects.filter(user=user):
        if nb.title.casefold().strip() == name.casefold():
            return nb, False
    return Notebook.objects.create(user=user, title=name), True
