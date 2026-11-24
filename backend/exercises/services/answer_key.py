"""The answer key printed in a Word paper or a PDF with text, read straight
from the file.

On 2026-11-24 the model, reading the pages as pictures, got 7 of 28 answers
of a real paper wrong: the key is a 22-column table of one-letter cells, and
it misread some and worked others out itself (-0,74 where the paper prints
-0,7). A Word file has the table as text, so it is read here, exactly, and
the model's reading is only a hint (see photo.read_problems).

A key is a header row of question numbers ("1 2 3 …", "1a 1b … 4d") over a
row of answers, or a column of numbers beside a column of answers. Numbers
that start again at 1, or switch between "3" and "3a", begin the next part:
the keys of a three-part paper are three runs, matched to its parts in order.
"""
import io
import re

_HEAD = re.compile(r'^(?:câu\s*)?(\d{1,2})\s*([a-dA-D])?\s*[).:]?$', re.I)
_LABEL = re.compile(r'^(câu|đáp\s*án|question|answer|ý)\b', re.I)
_TRUE = {'đ', 'd', 'đúng', 'dung', 'true', 't'}
_FALSE = {'s', 'sai', 'false', 'f'}


def _cells(row) -> list[str]:
    return [' '.join(c.text.split()) for c in row.cells]


def _heads(cells: list[str]):
    """[(number, letter or ''), ...] when every cell is a question number,
    a leading "Câu"/"Đáp án" cell aside; else None."""
    if cells and _LABEL.match(cells[0]) and not _HEAD.match(cells[0]):
        cells = cells[1:]
    heads = [_HEAD.match(c) for c in cells]
    if len(cells) < 2 or not all(heads):
        return None
    return [(int(m.group(1)), (m.group(2) or '').lower()) for m in heads]


def _pairs_of(table) -> list[tuple[tuple[int, str], str]]:
    rows = [_cells(r) for r in table.rows]
    pairs = []
    i = 0
    while i < len(rows) - 1:
        heads = _heads(rows[i])
        if heads is None or _heads(rows[i + 1]) is not None:
            i += 1
            continue
        values = rows[i + 1][-len(heads):]
        if len(values) == len(heads):
            pairs += list(zip(heads, values))
        i += 2
    if pairs:
        return pairs
    # Upright: "1 | B" on each row, under an optional "Câu | Đáp án".
    for cells in rows:
        if len(cells) == 2 and (m := _HEAD.match(cells[0])) and cells[1]:
            pairs.append(((int(m.group(1)), (m.group(2) or '').lower()), cells[1]))
    return pairs if len(pairs) >= 2 else []


def _runs(pairs) -> list[dict]:
    """The pairs cut into one run per part: {number: answer}, a true/false
    part's answer being {letter: bool}."""
    runs, last = [], None
    for (number, letter), value in pairs:
        kind = 'tf' if letter else 'one'
        restart = last is None or kind != last[0] or number < last[1] or (number == last[1] and not letter)
        if restart:
            runs.append({})
        last = (kind, number)
        run = runs[-1]
        if letter:
            mark = value.strip().lower()
            if mark in _TRUE or mark in _FALSE:
                run.setdefault(number, {})[letter] = mark in _TRUE
        elif value.strip():
            run[number] = value.strip()
    return [r for r in runs if r]


def key_from_docx(data: bytes) -> list[dict]:
    """The paper's key as runs, one per part, in order; [] when it has none
    this can read."""
    try:
        from docx import Document
        document = Document(io.BytesIO(data))
    except Exception:
        return []
    pairs = []
    for table in document.tables:
        pairs += _pairs_of(table)
    return _runs(pairs)


_KEY_HEADING = re.compile(r'(đáp\s*án|answer\s*key)', re.I)
_DIGITS = re.compile(r'^\d{1,2}$')
_ROW_SLACK = 2.0          # points: fragments this close in height are one line
_LONG = 8                 # a fragment longer than this is prose, not a key cell


def key_from_pdf(data: bytes) -> list[dict]:
    """The key of a PDF that has text (one saved from Word, not a scan),
    read from where its words sit, as runs like key_from_docx; [] when
    there is no "Đáp án" heading or no key under it.

    Text alone is not enough: a narrow cell wraps, so 180 comes out as
    "18" and "0" on two lines. Each cell keeps its place across the page,
    so the pieces are put back together by column."""
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(data))
    except Exception:
        return []
    pieces = []           # (page, -y, x, text)
    for number, page in enumerate(reader.pages):
        shown = {}

        def before(op, args, cm, tm):
            # Where each show-text operator writes: pypdf hands a piece it
            # joined to the line before over with no matrix (when the font
            # is set before the position, as Word writes), so keep this one.
            if op in (b'Tj', b'TJ', b"'", b'"'):
                shown['at'] = (cm, tm)

        def visit(text, cm, tm, font, size, number=number):
            if not (text and text.strip()):
                return
            if not any(tm[4:]) and not any(cm[4:]) and 'at' in shown:
                cm, tm = shown['at']
            x = cm[0] * tm[4] + cm[2] * tm[5] + cm[4]
            y = cm[1] * tm[4] + cm[3] * tm[5] + cm[5]
            pieces.append((number, -y, x, ' '.join(text.split())))
        try:
            page.extract_text(visitor_operand_before=before, visitor_text=visit)
        except Exception:
            return []
    pieces.sort()
    heads = [i for i, p in enumerate(pieces) if _KEY_HEADING.search(p[3]) and len(p[3]) <= 30]
    if not heads:
        return []
    rows = _rows(pieces[heads[-1] + 1:])
    pairs = []
    for block in _blocks(rows):
        pairs += _block_pairs(block)
    return _runs(pairs)


def _rows(pieces):
    rows = []
    for page, neg_y, x, text in pieces:
        if rows and rows[-1][0] == page and abs(rows[-1][1] - neg_y) <= _ROW_SLACK:
            rows[-1][2].append((x, text))
        else:
            rows.append((page, neg_y, [(x, text)]))
    return [(page, neg_y, sorted(cells)) for page, neg_y, cells in rows]


def _starts_table(cells) -> bool:
    texts = [t for _, t in cells]
    return len(texts) >= 2 and all(_DIGITS.match(t) for t in texts) and '1' in texts


def _blocks(rows):
    """The rows of each key table: from a row of question numbers to the
    row before the next one, or before the first line of prose."""
    blocks = []
    for page, neg_y, cells in rows:
        if any(len(t) > _LONG for _, t in cells):
            if blocks:
                break         # prose after the key: it is over
            continue
        if _starts_table(cells):
            blocks.append([(page, neg_y, cells)])
        elif blocks:
            blocks[-1].append((page, neg_y, cells))
    return blocks


def _block_pairs(block):
    """((number, letter), answer) for each column of one key table. The
    columns are the x positions of its pieces; a column reads down: its
    number, a lower-case letter under it for a true/false statement, then
    its answer, wrapped pieces joined."""
    first = sorted(x for x, _ in block[0][2])
    gaps = [b - a for a, b in zip(first, first[1:])] or [20.0]
    slack = max(2.0, min(8.0, 0.35 * min(gaps)))
    columns: list[list] = []
    for order, (page, neg_y, cells) in enumerate(block):
        for x, text in cells:
            near = min(columns, key=lambda c: abs(c[0] - x), default=None)
            if near is not None and abs(near[0] - x) <= slack:
                near[1].append((order, text))
            else:
                columns.append([x, [(order, text)]])
    pairs = []
    for _, column in sorted(columns, key=lambda c: c[0]):
        texts = [t for _, t in sorted(column, key=lambda p: p[0])]
        if not texts or not _DIGITS.match(texts[0]):
            continue
        number, rest, letter = int(texts[0]), texts[1:], ''
        if rest and re.fullmatch(r'[a-d]', rest[0]):
            letter, rest = rest[0], rest[1:]
        value = ''.join(rest)
        if value:
            pairs.append(((number, letter), value))
    return pairs


_NUMBER = re.compile(r'(\d{1,2})\s*$')


def apply_key(questions: list[dict], parts: list[str], runs: list[dict]) -> bool:
    """Each question's answer from the key, by its part and number. Used only
    when the key has one run per part (a one-part paper: one run), so a key
    that does not fit the paper is never half-applied. True when applied."""
    names = []
    for part in parts:
        if part not in names:
            names.append(part)
    if not runs or len(runs) != max(1, len(names)):
        return False
    applied = False
    for question, part in zip(questions, parts):
        number = _NUMBER.search(question['label'])
        run = runs[names.index(part)] if names else runs[0]
        if number and int(number.group(1)) in run:
            answer = run[int(number.group(1))]
            question['answer'] = answer.upper() if isinstance(answer, str) and re.fullmatch(r'[A-Da-d]', answer) else answer
            applied = True
    return applied
