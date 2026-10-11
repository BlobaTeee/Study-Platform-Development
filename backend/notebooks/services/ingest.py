from .document_extract import extract_text_from_document
from .textnorm import clean_summary, normalise_text
from .ai_provider import get_ai_provider

EMPTY_TEXT_MESSAGES = {
    'pdf': 'No text could be extracted. The PDF may be scanned images only.',
    'docx': 'No text could be extracted. The Word file may be empty or image-only.',
    'pptx': 'No text could be extracted. The presentation may have no text on slides.',
}


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


def process_source(source) -> None:
    """Extract text from document and optionally generate summary with AI provider."""
    file_type = getattr(source, 'file_type', None) or 'pdf'
    try:
        path = source.file.path
        text, page_count = extract_text_from_document(path, file_type)
        text = normalise_text(text)
        source.page_count = page_count
        source.extracted_text = text

        if text.strip():
            _read(source, text)
            source.status = 'ready'
        else:
            source.status = 'failed'
            source.error_message = EMPTY_TEXT_MESSAGES.get(
                file_type, 'No text could be extracted from this file.'
            )
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
