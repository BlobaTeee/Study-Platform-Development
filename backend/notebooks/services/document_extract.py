import os

from .pdf_extract import extract_text_from_pdf

ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.pptx'}


def file_type_from_filename(filename: str) -> str | None:
    ext = os.path.splitext(filename.lower())[1]
    if ext == '.pdf':
        return 'pdf'
    if ext == '.docx':
        return 'docx'
    if ext == '.pptx':
        return 'pptx'
    return None


def title_from_filename(filename: str) -> str:
    return os.path.splitext(filename)[0]


def extract_text_from_document(file_path: str, file_type: str) -> tuple[str, int]:
    """Return (full_text, page_or_slide_count) for pdf, docx, or pptx."""
    if file_type == 'pdf':
        return extract_text_from_pdf(file_path)
    if file_type == 'docx':
        return _extract_docx(file_path)
    if file_type == 'pptx':
        return _extract_pptx(file_path)
    raise ValueError(f'Unsupported file type: {file_type}')


def _extract_docx(file_path: str) -> tuple[str, int]:
    from docx import Document

    doc = Document(file_path)
    parts: list[str] = []

    for para in doc.paragraphs:
        text = (para.text or '').strip()
        if text:
            parts.append(text)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text = (cell.text or '').strip()
                if text:
                    parts.append(text)

    full_text = '\n\n'.join(parts).strip()
    # Word docs have no page count without rendering; use 0 in DB (UI hides "pages")
    return full_text, 0


def _extract_pptx(file_path: str) -> tuple[str, int]:
    from pptx import Presentation

    prs = Presentation(file_path)
    slides: list[str] = []

    for slide in prs.slides:
        slide_parts: list[str] = []
        for shape in slide.shapes:
            if not hasattr(shape, 'text'):
                continue
            text = (shape.text or '').strip()
            if text:
                slide_parts.append(text)
        if slide_parts:
            slides.append('\n'.join(slide_parts))

    full_text = '\n\n'.join(slides).strip()
    return full_text, len(prs.slides)
