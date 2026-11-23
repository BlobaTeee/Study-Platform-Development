"""Figures cut out of an exam page, so a practice problem shows a structural
formula or a graph as printed rather than as a description of it.

Reading a page (photo.read_problems), the model writes each figure into the
question as [Figure n: description] and gives where it is: the page and a
box in thousandths of the page's height and width (Gemini's own box format,
[ymin, xmin, ymax, xmax]). The page is drawn here and the box cut out as a
PNG data URL. The description stays in the problem's text, so the grader,
which reads text only, still knows what the figure shows; the page puts the
picture in its place (components/math-text.tsx).

A photo is cut directly. A PDF (a Word file arrives as one, see
photo.docx_to_pdf) is drawn page by page by LibreOffice; without it there
are no pictures and the descriptions show instead.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_PER_QUESTION = 4
#: Pixel width a PDF page is drawn at: sharp enough for subscripts in a crop.
RENDER_WIDTH = 1700
RENDER_SECONDS = 90
#: Margin added around the model's box, as a share of the page. The boxes
#: come back a little tight (on 2026-11-23 one clipped a structure's last OH
#: group), and a line of the question's own text in the margin costs less
#: than a figure missing a piece.
PAD_X, PAD_Y = 0.02, 0.025
#: A box smaller than this share of the page is a mistake, not a figure.
MIN_AREA = 0.0015
MAX_SIDE = 1200
MAX_DATA_URL_CHARS = 800_000
PREFIX = 'data:image/png;base64,'


def boxes_of(item: dict) -> list[tuple[int, tuple[float, float, float, float]]]:
    """The (page, box) pairs a read question gives, the unusable ones
    dropped. The box is [ymin, xmin, ymax, xmax] in thousandths."""
    out = []
    raw = item.get('figures') if isinstance(item.get('figures'), list) else []
    for fig in raw[:MAX_PER_QUESTION]:
        if not isinstance(fig, dict):
            out.append(None)
            continue
        box, page = fig.get('box'), fig.get('page', 1)
        try:
            page = int(page)
            ymin, xmin, ymax, xmax = (min(1000.0, max(0.0, float(v))) for v in box)
        except (TypeError, ValueError):
            out.append(None)
            continue
        if page < 1 or ymax <= ymin or xmax <= xmin:
            out.append(None)
            continue
        out.append((page, (ymin / 1000, xmin / 1000, ymax / 1000, xmax / 1000)))
    return out


def cut(data: bytes, mime: str, wanted: list[list]) -> list[list[str | None]]:
    """For each question's boxes (from `boxes_of`), the figures as PNG data
    URLs, None where one could not be cut. Pages are drawn once each."""
    pages = {b[0] for boxes in wanted for b in boxes if b}
    if not pages:
        return [[None] * len(boxes) for boxes in wanted]
    try:
        drawn = _pages(data, mime, pages)
    except Exception:  # noqa: BLE001 - no pictures is the fallback, never an error
        logger.warning('Drawing the pages for figures failed', exc_info=True)
        drawn = {}
    return [[_crop(drawn.get(b[0]), b[1]) if b else None for b in boxes] for boxes in wanted]


def _pages(data: bytes, mime: str, pages: set[int]) -> dict:
    from PIL import Image, ImageOps
    if mime.startswith('image/'):
        try:
            image = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
            return {1: image.convert('RGB')}
        except Exception:  # noqa: BLE001 - e.g. HEIC without its plugin
            return {}
    if mime == 'application/pdf':
        return _draw_pdf(data, pages)
    return {}


def _draw_pdf(pdf: bytes, pages: set[int]) -> dict:
    """The asked pages of a PDF as images, drawn by LibreOffice in one run
    per page shape (its export takes one pixel size for every file)."""
    from PIL import Image
    from pypdf import PdfReader, PdfWriter
    from .photo import soffice

    command = soffice()
    if not command:
        return {}
    reader = PdfReader(io.BytesIO(pdf))
    drawn = {}
    with tempfile.TemporaryDirectory() as tmp:
        by_size: dict[int, list[tuple[int, Path]]] = {}
        for number in sorted(p for p in pages if 1 <= p <= len(reader.pages)):
            page = reader.pages[number - 1]
            width, height = float(page.mediabox.width), float(page.mediabox.height)
            if page.get('/Rotate', 0) % 180:
                width, height = height, width
            pixel_height = round(RENDER_WIDTH * height / width) if width else RENDER_WIDTH
            path = Path(tmp) / f'page-{number}.pdf'
            writer = PdfWriter()
            writer.add_page(page)
            with path.open('wb') as fh:
                writer.write(fh)
            by_size.setdefault(pixel_height, []).append((number, path))
        for pixel_height, files in by_size.items():
            options = json.dumps({'PixelWidth': {'type': 'long', 'value': str(RENDER_WIDTH)},
                                  'PixelHeight': {'type': 'long', 'value': str(pixel_height)}})
            try:
                subprocess.run([command, '--headless', '--norestore', '--nologo',
                                f'-env:UserInstallation={Path(tmp, "profile").as_uri()}',
                                '--convert-to', f'png:draw_png_Export:{options}', '--outdir', tmp,
                                *[str(p) for _, p in files]],
                               capture_output=True, timeout=RENDER_SECONDS, check=False)
            except (OSError, subprocess.SubprocessError):
                continue
            for number, path in files:
                png = path.with_suffix('.png')
                if png.exists():
                    with Image.open(png) as image:
                        drawn[number] = image.convert('RGB')
    return drawn


def _crop(image, box) -> str | None:
    if image is None:
        return None
    ymin, xmin, ymax, xmax = box
    if (ymax - ymin) * (xmax - xmin) < MIN_AREA:
        return None
    w, h = image.size
    left, top = max(0, int((xmin - PAD_X) * w)), max(0, int((ymin - PAD_Y) * h))
    right, bottom = min(w, int((xmax + PAD_X) * w)), min(h, int((ymax + PAD_Y) * h))
    return _data_url(image.crop((left, top, right, bottom)))


def _data_url(image) -> str | None:
    image = image.copy()
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    image.save(out, 'PNG', optimize=True)
    url = PREFIX + base64.b64encode(out.getvalue()).decode('ascii')
    return url if len(url) <= MAX_DATA_URL_CHARS else None


def clean(value) -> str | None:
    """A figure the browser sent back, kept only if it really is a picture:
    decoded, opened and written out again as a PNG, so nothing else rides
    along in it. None for anything else."""
    from PIL import Image
    if not isinstance(value, str) or not value.startswith('data:image/') or len(value) > MAX_DATA_URL_CHARS:
        return None
    try:
        raw = base64.b64decode(value.split(',', 1)[1], validate=True)
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            return _data_url(image.convert('RGB'))
    except Exception:  # noqa: BLE001
        return None
