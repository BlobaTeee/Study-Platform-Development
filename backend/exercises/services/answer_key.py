"""The answer key printed in a Word paper, read straight from its tables.

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
