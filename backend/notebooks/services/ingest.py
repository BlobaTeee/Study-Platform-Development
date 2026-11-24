from django.utils.translation import gettext_noop

from .document_extract import extract_text_from_document
from .textnorm import clean_summary, normalise_text
from .ai_provider import get_ai_provider

# Stored as written here; the serializer shows them in the reader's language.
EMPTY_TEXT_MESSAGES = {
    'pdf': gettext_noop('No text could be extracted. The PDF may be scanned images only.'),
    'docx': gettext_noop('No text could be extracted. The Word file may be empty or image-only.'),
    'pptx': gettext_noop('No text could be extracted. The presentation may have no text on slides.'),
}
NO_TEXT = gettext_noop('No text could be extracted from this file.')
STALLED = gettext_noop('Reading this file stopped part way. Remove it and upload it again.')
#: A background read (OCR of a scanned book) takes minutes; one still going
#: after this long died with the server that ran it.
STALLED_MINUTES = 20


def fail_stalled(notebook) -> None:
    """Documents whose background read was cut off (the server restarted)
    would show as processing for ever: say so instead."""
    from datetime import timedelta
    from django.utils import timezone
    notebook.sources.filter(status='processing',
                            updated_at__lt=timezone.now() - timedelta(minutes=STALLED_MINUTES)
                            ).update(status='failed', error_message=STALLED)


def _read(source, text: str) -> None:
    """Overview and main ideas from one request (key_points.read_document)."""
    from .key_points import read_document
    out = read_document(text, source.title)
    source.gemini_summary = out['summary']
    source.key_points = out['key_points']


def finish_text_source(source) -> None:
    """Mark a source whose text is already in hand as ready, with a summary
    if a provider is reachable. Shared by pasted text and fetched pages."""
    _read(source, source.extracted_text)
    source.status = 'ready'
    source.save()


def needs_ocr(path: str) -> bool:
    """A PDF of page pictures that Tesseract can read: its text comes from
    OCR, which takes minutes, so it is read in the background."""
    from . import ocr
    from .pdf_extract import extract_text_from_pdf
    try:
        text, page_count = extract_text_from_pdf(path)
    except Exception:
        return False
    return ocr.is_scanned(normalise_text(text), page_count) and ocr.available()


def process_in_background(source) -> None:
    """process_source on a thread; the source stays 'processing' until it ends."""
    import threading

    def run():
        from django.db import close_old_connections
        try:
            process_source(source)
        finally:
            close_old_connections()

    threading.Thread(target=run, daemon=True).start()


def process_source(source) -> None:
    """Extract text from document and optionally generate summary with AI provider."""
    from . import ocr
    file_type = getattr(source, 'file_type', None) or 'pdf'
    try:
        path = source.file.path
        text, page_count = extract_text_from_document(path, file_type)
        text = normalise_text(text)
        if file_type == 'pdf' and ocr.is_scanned(text, page_count) and ocr.available():
            text = normalise_text(ocr.read_pdf(path))
        source.page_count = page_count
        source.extracted_text = text

        if text.strip():
            _read(source, text)
            source.status = 'ready'
        else:
            source.status = 'failed'
            source.error_message = EMPTY_TEXT_MESSAGES.get(file_type, NO_TEXT)
    except Exception as exc:
        source.status = 'failed'
        source.error_message = str(exc)

    source.save(
        update_fields=[
            'page_count',
            'extracted_text',
            'gemini_summary',
            'status',
            'error_message',
            'updated_at',
        ]
    )


process_pdf_source = process_source
