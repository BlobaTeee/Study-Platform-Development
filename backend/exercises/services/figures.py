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

The model's box is rough: on 2026-11-23 one took in the question's line and
two of its options and cut off the formula's right end. In a PDF a figure
is usually a picture placed on the page, and where it sits is written in the
page itself, so the box is moved onto the pictures it covers (`_snap`). A
figure drawn with lines, a scanned page or a photo has no such pictures; there
the box is fitted to the ink it lands on, between the blank lines that part a
figure from the question's text (`_fit`).
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
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
#: Margin around a box moved onto the page's own pictures. They are exact,
#: and the question's lines sit close above and below them.
SNAP_PAD_X, SNAP_PAD_Y = 0.004, 0.0015
#: A picture belongs to a figure when this share of it lies in the model's box.
SNAP_INSIDE = 0.5
#: ...and the pictures together must fill this share of the box, or the box
#: was around something else (a drawing with a small picture in it).
SNAP_FILLS = 0.25
#: A picture this large is a scanned page, not a figure.
SNAP_MAX_AREA = 0.6
#: How far past the model's box a figure's ink is looked for, as a share of
#: the page. On a scanned exam on 2026-11-27 the boxes were off by up to 0.035
#: of the page's height and 0.06 of its width.
FIT_REACH_X, FIT_REACH_Y = 0.08, 0.05
#: Grey darker than this is ink.
FIT_INK = 160
#: A row or column with fewer ink pixels than this is blank (a scan's specks).
FIT_SPECK = 2
#: Blank columns narrower than this share of the page are inside a figure (a
#: label beside its drawing); blank rows this short too. Between a figure and
#: the question's lines there were 7 blank rows of 2404 on that exam.
FIT_GAP_X, FIT_GAP_Y = 0.015, 0.0015
#: Margin around a fitted box.
FIT_PAD_X, FIT_PAD_Y = 0.004, 0.002
#: A box smaller than this share of the page is a mistake, not a figure.
MIN_AREA = 0.0015
MAX_SIDE = 1200
MAX_DATA_URL_CHARS = 800_000
PREFIX = 'data:image/png;base64,'


_TAG = re.compile(r'\[Figure\s*(\d+)\s*:')


#: A bracketed description: starts with a letter and runs to a few words,
#: unlike maths such as [B,SC,D], the tags themselves, a table copied as
#: text ([Table: ...]) or a variation table's interval ([On (-2; 1): ...]).
_DESCRIBED = re.compile(r'\[(?!Figure\s*\d)(?!unreadable\])(?!(?:Table|Bảng|On|Trên)\b)'
                        r'([A-Za-zÀ-ỹ][^\[\]$]{25,})\]')


def tag_untagged(text: str, cut: int) -> str:
    """A question with a figure cut but no [Figure n: ...] tag: its bracketed
    descriptions become the tags, in order. On 2026-11-26 the reader wrote
    "[Ellipse with semi-major axis, ...]" for the paper's drawing, so the
    drawing, cut from the page, was dropped and the test showed only words.
    A text that has a tag, or no figure cut, is left as it is."""
    if not cut or tags_in(text):
        return text
    n = 0

    def tag(m):
        nonlocal n
        if n >= cut:
            return m.group(0)
        n += 1
        return f'[Figure {n}: {m.group(1).strip()}]'
    return _DESCRIBED.sub(tag, text)


#: Words by which a question points to a figure printed with it.
_POINTS = re.compile(r'hình\s+vẽ|hình\s+(?:bên|dưới|sau)|như\s+hình|đồ\s+thị\s+(?:dưới|bên|sau|như|ở)'
                     r'|the\s+(?:figure|graph|diagram)\s+(?:below|above|shown)|shown\s+(?:below|in\s+the\s+figure)',
                     re.I)
#: A table the reader copied as text (a Markdown row, or described).
_TABLE = re.compile(r'^\s*\||\[(?:Table|Bảng)\b', re.M)


def points_to_figure(text: str) -> bool:
    """Whether a question says it has a figure ("như hình vẽ", "đồ thị dưới
    đây") and is not a table, whose box would be the table's lines."""
    return bool(_POINTS.search(text or '')) and not _TABLE.search(text or '')


def tags_in(text: str) -> set[int]:
    """The figure numbers a text has a [Figure n: ...] tag for."""
    return {int(n) for n in _TAG.findall(text or '')}


def renumber(texts: list[str]) -> list[str]:
    """One question's texts (stem, options, statements) with its figures
    numbered 1, 2, ... in the order of their numbers, as its boxes are. On
    2026-11-27 the reader numbered a question's only figure 2, counting the
    paper's figures, and the figure was dropped for want of a second box."""
    numbers = sorted(set().union(*(tags_in(t) for t in texts)))
    if numbers == list(range(1, len(numbers) + 1)):
        return texts
    new = {old: n for n, old in enumerate(numbers, 1)}
    return [_TAG.sub(lambda m: f'[Figure {new[int(m.group(1))]}:', t or '') for t in texts]


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
    placed = {}
    if mime == 'application/pdf' and drawn:
        try:
            placed = placed_pictures(data, set(drawn))
        except Exception:  # noqa: BLE001 - the model's box is the fallback
            logger.warning('Reading where the pictures sit failed', exc_info=True)
    out = []
    for boxes in wanted:
        row = []
        for b in boxes:
            if not b:
                row.append(None)
                continue
            image = drawn.get(b[0])
            snapped = _snap(b[1], placed.get(b[0], []))
            fitted = None if snapped or image is None else _fit(image, b[1])
            if snapped:
                row.append(_crop(image, snapped, SNAP_PAD_X, SNAP_PAD_Y))
            elif fitted:
                row.append(_crop(image, fitted, FIT_PAD_X, FIT_PAD_Y))
            else:
                row.append(_crop(image, b[1]))
        out.append(row)
    return out


def _runs(counts, gap: int) -> list[tuple[int, int]]:
    """The [start, end) runs where counts show ink, joined across blanks
    shorter than `gap`."""
    runs = []
    for i, inked in enumerate(counts >= FIT_SPECK):
        if not inked:
            continue
        if runs and i - runs[-1][1] < gap:
            runs[-1][1] = i + 1
        else:
            runs.append([i, i + 1])
    return [tuple(r) for r in runs]


def _most_of(runs, lo: int, hi: int):
    """The run that overlaps [lo, hi) the most, or None."""
    best = max(runs, key=lambda r: min(hi, r[1]) - max(lo, r[0]), default=None)
    return best if best and min(hi, best[1]) > max(lo, best[0]) else None


def _fit(image, box):
    """The model's box fitted to the ink it lands on, or None to keep it.

    Within the box's columns, the rows of ink parted by blank rows are the
    question's lines and the figure; the one the box covers most is the
    figure. Within those rows, its columns are found the same way, then its
    rows again within its columns, so a figure the box cut off is found
    whole. A fit that runs to the edge of where it looked, or comes out far
    smaller or larger than the box, is not a figure standing on its own (a
    dark photo, a drawing inside a table), and the box is kept."""
    import numpy as np

    w, h = image.size
    ymin, xmin, ymax, xmax = box
    top, left = max(0, int((ymin - FIT_REACH_Y) * h)), max(0, int((xmin - FIT_REACH_X) * w))
    bottom, right = min(h, int((ymax + FIT_REACH_Y) * h)), min(w, int((xmax + FIT_REACH_X) * w))
    ink = np.asarray(image.crop((left, top, right, bottom)).convert('L')) < FIT_INK
    if not ink.size:
        return None
    gap_x, gap_y = max(1, round(FIT_GAP_X * w)), max(1, round(FIT_GAP_Y * h))
    by0, by1 = int(ymin * h) - top, int(ymax * h) - top
    bx0, bx1 = int(xmin * w) - left, int(xmax * w) - left

    rows = _most_of(_runs(ink[:, bx0:bx1].sum(axis=1), gap_y), by0, by1)
    if not rows:
        return None
    cols = _most_of(_runs(ink[rows[0]:rows[1]].sum(axis=0), gap_x), bx0, bx1)
    if not cols:
        return None
    rows = _most_of(_runs(ink[:, cols[0]:cols[1]].sum(axis=1), gap_y), rows[0], rows[1])
    if not rows:
        return None
    if rows[0] == 0 and top > 0 or cols[0] == 0 and left > 0 \
            or rows[1] == ink.shape[0] and bottom < h or cols[1] == ink.shape[1] and right < w:
        return None
    fitted = ((top + rows[0]) / h, (left + cols[0]) / w, (top + rows[1]) / h, (left + cols[1]) / w)
    ratio = (fitted[2] - fitted[0]) * (fitted[3] - fitted[1]) / ((ymax - ymin) * (xmax - xmin))
    return fitted if SNAP_FILLS <= ratio <= 1 / SNAP_FILLS else None


def _snap(box, pictures):
    """The model's box moved onto the page's pictures it covers, or None
    to keep it. Boxes are (ymin, xmin, ymax, xmax), shares of the page."""
    ymin, xmin, ymax, xmax = box
    area = (ymax - ymin) * (xmax - xmin)
    inside = []
    for p in pictures:
        own = (p[2] - p[0]) * (p[3] - p[1])
        if own <= 0 or own > SNAP_MAX_AREA:
            continue
        overlap = max(0.0, min(ymax, p[2]) - max(ymin, p[0])) * max(0.0, min(xmax, p[3]) - max(xmin, p[1]))
        if overlap >= SNAP_INSIDE * own:
            inside.append(p)
    if not inside or area <= 0:
        return None
    union = (min(p[0] for p in inside), min(p[1] for p in inside),
             max(p[2] for p in inside), max(p[3] for p in inside))
    if sum((p[2] - p[0]) * (p[3] - p[1]) for p in inside) < SNAP_FILLS * area:
        return None
    return union


def placed_pictures(pdf: bytes, pages: set[int]) -> dict[int, list[tuple]]:
    """Where each picture is drawn on the asked pages, as (ymin, xmin, ymax,
    xmax) shares of the page from its top left. Only pictures drawn straight
    on the page are found; a rotated page gives none."""
    from pypdf import PdfReader
    from pypdf.generic import ContentStream

    reader = PdfReader(io.BytesIO(pdf))
    out = {}
    for number in pages:
        if not 1 <= number <= len(reader.pages):
            continue
        page = reader.pages[number - 1]
        if page.get('/Rotate', 0) % 360:
            continue
        resources = page.get('/Resources')
        xobjects = resources.get_object().get('/XObject', {}) if resources else {}
        xobjects = xobjects.get_object() if xobjects else {}
        box = page.mediabox
        left, bottom = float(box.left), float(box.bottom)
        width, height = float(box.width), float(box.height)
        if width <= 0 or height <= 0:
            continue
        ctm, saved, found = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0), [], []
        for operands, op in ContentStream(page.get_contents(), reader).operations:
            if op == b'q':
                saved.append(ctm)
            elif op == b'Q':
                ctm = saved.pop() if saved else ctm
            elif op == b'cm' and len(operands) == 6:
                ctm = _times(tuple(float(v) for v in operands), ctm)
            elif op == b'Do' and operands:
                xobject = xobjects.get(operands[0])
                if xobject is None or xobject.get_object().get('/Subtype') != '/Image':
                    continue
                a, b, c, d, e, f = ctm
                corners = [(a * u + c * v + e, b * u + d * v + f) for u, v in ((0, 0), (1, 0), (0, 1), (1, 1))]
                xs, ys = [x for x, _ in corners], [y for _, y in corners]
                found.append(((bottom + height - max(ys)) / height, (min(xs) - left) / width,
                              (bottom + height - min(ys)) / height, (max(xs) - left) / width))
        out[number] = found
    return out


def _times(m, n):
    """PDF matrix product m x n (m applied first)."""
    return (m[0] * n[0] + m[1] * n[2], m[0] * n[1] + m[1] * n[3],
            m[2] * n[0] + m[3] * n[2], m[2] * n[1] + m[3] * n[3],
            m[4] * n[0] + m[5] * n[2] + n[4], m[4] * n[1] + m[5] * n[3] + n[5])


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


def _crop(image, box, pad_x=PAD_X, pad_y=PAD_Y) -> str | None:
    if image is None:
        return None
    ymin, xmin, ymax, xmax = box
    if (ymax - ymin) * (xmax - xmin) < MIN_AREA:
        return None
    w, h = image.size
    left, top = max(0, int((xmin - pad_x) * w)), max(0, int((ymin - pad_y) * h))
    right, bottom = min(w, int((xmax + pad_x) * w)), min(h, int((ymax + pad_y) * h))
    return _data_url(image.crop((left, top, right, bottom)))


def _data_url(image) -> str | None:
    image = image.copy()
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    image.save(out, 'PNG', optimize=True)
    url = PREFIX + base64.b64encode(out.getvalue()).decode('ascii')
    return url if len(url) <= MAX_DATA_URL_CHARS else None


def image_of(value) -> tuple[bytes, str] | None:
    """A stored figure as (bytes, mime) to send to the model, or None."""
    if not isinstance(value, str) or not value.startswith(PREFIX):
        return None
    try:
        return base64.b64decode(value[len(PREFIX):], validate=True), 'image/png'
    except ValueError:
        return None


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
