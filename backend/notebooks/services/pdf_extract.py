from pypdf import PdfReader


def extract_text_from_pdf(file_path: str) -> tuple[str, int]:
    """Return (full_text, page_count) from a PDF on disk."""
    reader = PdfReader(file_path)
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ''
        pages.append(text)
    return '\n\n'.join(pages).strip(), len(reader.pages)
