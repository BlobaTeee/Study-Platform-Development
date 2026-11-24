"""Text for a scanned PDF, read off its page pictures by Tesseract.

A scanned book has no text layer: every page is one photograph, and pypdf
finds nothing. Tesseract (installed beside the app, like LibreOffice) reads
each page's picture, Vietnamese and English, on this machine: no model
request is spent, so a 373-page book does not use up a day's AI quota.
It is slow (about a second a page per core), so callers run it in the
background (see views.upload_pdf).
"""
import functools
import io
import logging
import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings

logger = logging.getLogger(__name__)

LANGUAGES = 'vie+eng'
PAGE_SECONDS = 90          # one page that takes longer is skipped, not waited on
MIN_CHARS_PER_PAGE = 40    # below this a PDF counts as scanned


def command() -> str | None:
    configured = getattr(settings, 'TESSERACT_COMMAND', '') or 'tesseract'
    return shutil.which(configured)


@functools.lru_cache(maxsize=1)
def available() -> bool:
    """Tesseract is installed with the languages it needs."""
    tesseract = command()
    if not tesseract:
        return False
    try:
        listed = subprocess.run([tesseract, '--list-langs'], capture_output=True, text=True,
                                timeout=20, check=False).stdout.split()
    except (OSError, subprocess.TimeoutExpired):
        return False
    return all(lang in listed for lang in LANGUAGES.split('+'))


def is_scanned(text: str, page_count: int) -> bool:
    """Too little text for the pages it has: pictures of pages, not text."""
    return page_count > 0 and len(text.strip()) < MIN_CHARS_PER_PAGE * page_count


def _page_picture(page) -> bytes | None:
    """The biggest picture on a page: on a scanned page, the page itself."""
    try:
        pictures = list(page.images)
    except Exception:
        return None
    if not pictures:
        return None
    biggest = max(pictures, key=lambda p: len(p.data))
    try:
        out = io.BytesIO()
        biggest.image.convert('L').save(out, format='PNG')
        return out.getvalue()
    except Exception:
        return None


def _read_picture(tesseract: str, picture: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
        tmp.write(picture)
        path = tmp.name
    try:
        # One thread per Tesseract: the pages already run side by side.
        env = {**os.environ, 'OMP_THREAD_LIMIT': '1'}
        run = subprocess.run([tesseract, path, 'stdout', '-l', LANGUAGES], capture_output=True,
                             text=True, timeout=PAGE_SECONDS, check=False, env=env)
        return run.stdout
    except (OSError, subprocess.TimeoutExpired):
        return ''
    finally:
        os.unlink(path)


def read_pdf(path: str, first_pages: int | None = None) -> str:
    """The text of a scanned PDF, page by page in order; '' when Tesseract
    is missing. first_pages: only that many from the start (a quick look)."""
    from pypdf import PdfReader

    tesseract = command()
    if not tesseract:
        return ''
    reader = PdfReader(path)
    pages = reader.pages[:first_pages] if first_pages else reader.pages
    limit = int(getattr(settings, 'OCR_MAX_PAGES', 500))
    pages = list(pages)[:limit]
    workers = max(1, min(8, (os.cpu_count() or 2) - 1))

    # The pictures are taken out one by one (one reader is not shared across
    # threads); only Tesseract runs side by side.
    pictures = [_page_picture(page) for page in pages]

    def one(picture):
        return _read_picture(tesseract, picture) if picture else ''

    with ThreadPoolExecutor(max_workers=workers) as pool:
        texts = list(pool.map(one, pictures))
    return '\n\n'.join(t.strip() for t in texts if t.strip())
