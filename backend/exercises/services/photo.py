"""A photographed problem, or a file of them, read into text for the student to check.

A photo or a PDF goes to the model as it is, so a scanned page reads like a
photo. A Word file is turned into a PDF by LibreOffice when it is installed,
so its ChemDraw and MathType objects (Windows metafiles the model cannot
read) arrive drawn as on paper. Without LibreOffice its text is taken out
here, in reading order, with each picture the model can read sent alongside
and marked [Figure n] where it stands.

One request reads the photo, giving each question on it separately (an exam
page holds a dozen; the student picks one to practise); the photo itself is
not kept. Maths comes back in LaTeX ($...$ inline, $$...$$ on its own line) so
the page can show it as it was printed and the student can compare; a figure or table is described in
square brackets. The text is only a draft: the student corrects it and then
creates the problem from it as from any typed problem (problems.own_rubric),
so a misread digit never reaches the rubric unseen.
"""
import re

from django.conf import settings
from django.utils.translation import gettext as _

from . import figures
from .common import PracticeUnavailable, ask, items_of, printed_answer

DEFAULT_MAX_BYTES = 15 * 1024 * 1024
DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
MAX_DOCX_CHARS = 30000
MAX_TEXT_CHARS = 4000
MAX_QUESTIONS = 30
MAX_TITLE_CHARS = 80
MAX_LABEL_CHARS = 40
MAX_INSTRUCTION_CHARS = 400
MAX_DOCX_FIGURES = 20
DOCX_CONVERT_SECONDS = 90
#: Smaller pictures are bullets and logos, not figures.
MIN_FIGURE_BYTES = 300

PROMPT = """This photo or document should show problems a student wants to practise: homework, a
textbook page or an exam paper (a document may run over several pages). Copy each question out as text, exactly and completely, in the language it is
written in. A page with several questions gives several; a photo of one problem gives one.

- A question is everything answered together: a multiple-choice question with its options, or a
  true/false question with its shared stem AND all its statements a), b), c), d). Never split a
  question's options or statements into separate questions.
- Copy every given: numbers, units, conditions, the answer options, the question itself. Do
  not solve it and do not add anything that is not printed.
- Keep names, labels and numbering exactly as printed: if the options are n_2, n_1, n_4, n_3,
  write them in that order with those names.
- If a section's instruction tells how to answer (choose one option; true or false for each
  statement; a short numeric answer), give it as "instruction" on each of its questions, not
  in "text".
- Ignore everything handwritten: circled or ticked options, marks such as "Đ", "S", ✓, crossed
  out letters, numbers written in the margin. Copy only what is printed; a circled option
  would give the answer away.
- Leave out page headers and footers (candidate number, exam code, page numbers).
- An answer key printed in the paper (ĐÁP ÁN, a table of question numbers and answers) is not a
  question. Give each question its printed answer as "answer": the option's letter ("B"), each
  statement's mark ({"a": true, "b": false, "c": true, "d": true}; Đ is true, S is false), or the
  short answer as printed ("180"); null when the paper prints none. Never take an answer from
  handwriting.
- Write all mathematics in LaTeX: inline as $...$, a formula on its own line as $$...$$
  (fractions \\frac{a}{b}, roots \\sqrt{x}, powers x^{2}, indices x_{1}, integrals, sums,
  matrices with \\begin{pmatrix}...\\end{pmatrix}). Chemical formulas likewise ($H_2SO_4$).
- Write a unit after a number as its symbol (500 J, 2 Pa, 3 m/s), even where the paper spells it out.
- Everything you write, the square-bracket descriptions included, is in the
  same language as the problem: a Vietnamese problem gets Vietnamese descriptions (the
  examples below only show the form).
- Write a figure (a diagram, a structural formula, a graph, a picture) where it stands as
  [Figure n: what it shows, with the values and labels the question needs], n counting 1, 2, ...
  within that question; keep the word "Figure" in English, but write what it shows in the
  problem's language, e.g.
  [Figure 1: Right triangle ABC, right angle at C, AC = 3 cm, BC = 4 cm]. For each, in the same
  order, give in the question's "figures" where it is: {"page": its page in the document (1 for
  a photo), "box": [ymin, xmin, ymax, xmax]}, in thousandths of the page's height and width,
  around the whole figure and its labels but not the question's text.
- Copy a table as a Markdown table, one row per line (| Cặp | Zn²⁺/Zn | ... |, then | --- | ... |,
  then each row); a table is text, never a figure, so it gets no [Figure n] tag and no box.
  For a variation table (bảng biến thiên), give
  for each interval between the x values the sign of y' and the direction of the arrow of y,
  with the values at its ends, e.g. [On (-\\infty; -2): y' -, y decreases from 1 to -\\infty].
  Read each sign and each arrow from the photo; do not infer them.
- If part of a question cannot be read, write [unreadable] there rather than guessing. A
  question cut off at the edge of the photo is copied as far as it goes.

Also give the paper a short name, as "title", in its language, in sentence case (not capitals) and
at most 60 characters: from its
heading when it has one (the kind of test, the subject, the grade), e.g. "Đề ôn tập cuối kỳ 1 Hoá
học 12"; otherwise what its problems are about, e.g. "Bài tập rơi tự do".

If there is no problem in the photo (a selfie, a blank page, notes with no question), return
{"found": false, "questions": []}. Otherwise return
{"found": true, "title": "...", "questions": [{"label": "how the page numbers it, e.g. Câu 3 or Bài 2a, without
the part", "part": "the part it is in, its name and number only, e.g. Phần I or Part B (not its
title), given on every question of
that part, the first part's included; \"\" when the paper has no parts",
"instruction": "the section's instruction, or \"\"", "text": "...",
"answer": null, "figures": [{"page": 1, "box": [ymin, xmin, ymax, xmax]}]}]}
in the order they appear.

Return ONLY valid JSON."""


class NoProblemInPhoto(Exception):
    pass


class NotAnImage(Exception):
    pass


def image_type(data: bytes) -> str | None:
    """The file's type from its first bytes (never from the file name): an
    image, a PDF or a Word file."""
    if data[:5] == b'%PDF-':
        return 'application/pdf'
    if data[:4] == b'PK\x03\x04' and b'word/document.xml' in data[:65536]:
        return DOCX
    if data[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    if data[4:8] == b'ftyp' and data[8:12] in (b'heic', b'heix', b'hevc', b'heim', b'heis', b'mif1', b'msf1'):
        return 'image/heic'
    return None


def max_bytes() -> int:
    return int(getattr(settings, 'PROBLEM_PHOTO_MAX_BYTES', DEFAULT_MAX_BYTES))


def read_problems(data: bytes) -> tuple[list[dict], str]:
    """The questions in the photo, in order, as {label, instruction, text}; maths
    in LaTeX. The instruction is the section's (how to answer), shared by many.
    With them, a short name for the paper, from the same request ('' when the
    model gave none): the name a set picked from it starts with."""
    mime = image_type(data)
    if mime is None:
        raise NotAnImage(_('Use a photo (JPEG, PNG, WEBP or HEIC), a PDF or a Word file.'))
    if mime == DOCX and (pdf := docx_to_pdf(data)):
        data, mime = pdf, 'application/pdf'
    if mime == DOCX:
        text, pictures = _docx_contents(data)
        if not text:
            raise NoProblemInPhoto(_('No problem could be found in this file.'))
        note = FIGURES_NOTE.format(count=len(pictures)) if pictures else ''
        reply = ask(f'{PROMPT}\n\n{note}The document, as text:\n{text}', images=pictures or None, reading=True)
    else:
        reply = ask(PROMPT, images=[(data, mime)], reading=True)
    raw = items_of(reply, 'questions')
    if not raw and reply.get('text'):
        raw = [{'text': reply.get('text')}]        # an older reply shape: the whole photo as one
    questions, boxes, parts = [], [], []
    for item in raw[:MAX_QUESTIONS]:
        if not isinstance(item, dict):
            continue
        text = str(item.get('text') or '').strip()[:MAX_TEXT_CHARS]
        if text:
            label = str(item.get('label') or '').strip()[:MAX_LABEL_CHARS]
            instruction = str(item.get('instruction') or '').strip()[:MAX_INSTRUCTION_CHARS]
            question = {'label': label or str(len(questions) + 1), 'instruction': instruction, 'text': text}
            answer = printed_answer(item.get('answer'))
            if answer is not None:
                question['answer'] = answer        # the paper's own key, used for the answer key
            questions.append(question)
            boxes.append(figures.boxes_of(item))
            parts.append(_part_name(item.get('part')))
    _label_parts(questions, parts)
    for question in questions:
        question['text'] = _statement_letters(question['text'])
    if reply.get('found') is False or not questions:
        raise NoProblemInPhoto(_('No problem could be found in this photo. Try a closer, sharper photo of it.'))
    # A Word file read as text has no pages to cut from; its figures stay described.
    cuts = figures.cut(data, mime, boxes) if mime != DOCX else [[None] * len(b) for b in boxes]
    for question, cut in zip(questions, cuts):
        # [Figure n] is figures[n - 1]; None: not cut. A box the text has no
        # tag for is dropped: on 2026-11-23 a table, copied as text, also got
        # a box, which landed on the next question's lines; sent along to the
        # answer key it pulled that question's statements in.
        tagged = figures.tags_in(question['text'])
        question['figures'] = [url if n in tagged else None for n, url in enumerate(cut, 1)]
        while question['figures'] and question['figures'][-1] is None:
            question['figures'].pop()
    title = _title(reply.get('title'))
    return questions, title


_STATEMENT = re.compile(r'^(\s*)([A-Da-d])\)', re.M)


def _statement_letters(text: str) -> str:
    """Statements lettered the same way throughout: the reader once wrote
    "a)" and then "B) C) D)". When the first statement is lower case, so
    are the rest; options A) B) C) D) have no "a)" and stay as they are."""
    first = _STATEMENT.search(text)
    if not first or not first.group(2).islower():
        return text
    return _STATEMENT.sub(lambda m: m.group(1) + m.group(2).lower() + ')', text)


_ROMAN = re.compile(r'[IVXLC]+', re.I)
# The part's name and number alone: "PHẦN II. Câu trắc nghiệm đúng sai" is "PHẦN II".
_PART_HEAD = re.compile(r'^((?:phần|part|section|mục|chương)\s+(?:[IVXLC]+|\d+|[A-Z])\b)', re.I)
# A part the model wrote into the label anyway: "PHẦN II · Câu 1", "Part B: Q3".
_PART_IN_LABEL = re.compile(r'^(?:phần|part|section|mục)\s+\S+\s*[·:.,\-–—]?\s*', re.I)


def _part_name(value) -> str:
    """A part's name and number, as a name: "PHẦN II. Câu trắc nghiệm đúng
    sai" is "Phần II" (the model gave the whole heading on 2026-11-23)."""
    text = ' '.join(str(value or '').split())
    head = _PART_HEAD.match(text)
    if not head:
        return text.rstrip('.:·-–— ')[:MAX_LABEL_CHARS]
    word, number = head.group(1).split(' ', 1)
    return f'{word.capitalize()} {number.upper() if _ROMAN.fullmatch(number) else number}'


def _title(value) -> str:
    """The paper's name on one line; a name in capitals is written as a
    sentence, Roman numerals kept ("Đề kiểm tra cuối kỳ I ...")."""
    title = ' '.join(str(value or '').split())[:MAX_TITLE_CHARS]
    if not title.isupper():
        return title
    words = title.lower().split(' ')
    words = [w.upper() if _ROMAN.fullmatch(w) and len(w) <= 4 and i else w for i, w in enumerate(words)]
    return words[0][:1].upper() + ' '.join(words)[1:]


def _label_parts(questions: list[dict], parts: list[str]) -> None:
    """Every question named with its part ("Phần I · Câu 11") when the paper
    has more than one, so the parts read the same throughout: the model used
    to add the part only once the numbering restarted, leaving Part I bare.
    A question given no part is in the one before it."""
    current, filled = '', []
    for part in parts:
        current = part or current
        filled.append(current)
    if len({p for p in filled if p}) < 2:
        return
    for question, part in zip(questions, filled):
        if part:
            bare = _PART_IN_LABEL.sub('', question['label']) or question['label']
            question['label'] = f'{part} · {bare}'


FIGURES_NOTE = """The document's pictures are attached as {count} images, in order: [Picture 1] in
the text is the first image, [Picture 2] the second, and so on. Where a question has one,
describe it in square brackets at that place, as for a photo and in the problem's language,
with everything the question needs from it (a structural formula: its groups and how they are joined; a graph: its axes and
values). [Picture unreadable] is a picture that could not be sent.

"""


def soffice() -> str | None:
    """LibreOffice's command, if it is installed."""
    import shutil
    configured = getattr(settings, 'SOFFICE_PATH', '') or ''
    return configured if configured and shutil.which(configured) else shutil.which('soffice')


def docx_to_pdf(data: bytes) -> bytes | None:
    """A Word file as a PDF, drawn by LibreOffice; None when it is not
    installed or the conversion fails, and the text route is used instead.
    Each conversion gets its own profile folder: LibreOffice refuses to run
    twice on one profile, and two students may upload at once."""
    import subprocess
    import tempfile
    from pathlib import Path

    command = soffice()
    if not command:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / 'in.docx'
        src.write_bytes(data)
        try:
            subprocess.run([command, '--headless', '--norestore', '--nologo',
                            f'-env:UserInstallation={Path(tmp, "profile").as_uri()}',
                            '--convert-to', 'pdf', '--outdir', tmp, str(src)],
                           capture_output=True, timeout=DOCX_CONVERT_SECONDS, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        out = Path(tmp) / 'in.pdf'
        pdf = out.read_bytes() if out.exists() else b''
    return pdf if pdf.startswith(b'%PDF-') else None


def _docx_contents(data: bytes) -> tuple[str, list[tuple[bytes, str]]]:
    """A Word file's text in reading order (paragraphs and tables as they
    come, a table row on one line) and its pictures, each marked [Figure n]
    where it stands. A broken file reads as no text."""
    import io
    from docx import Document
    from docx.oxml.ns import qn

    try:
        doc = Document(io.BytesIO(data))
    except Exception:  # noqa: BLE001 - a broken file reads as no text
        return '', []
    pictures: list[tuple[bytes, str]] = []
    seen: dict[str, str] = {}
    t, tab, br, cr, mt = qn('w:t'), qn('w:tab'), qn('w:br'), qn('w:cr'), qn('m:t')
    blip, embed = qn('a:blip'), qn('r:embed')
    vml_image = '{urn:schemas-microsoft-com:vml}imagedata'

    def figure(rid: str | None) -> str:
        if not rid:
            return ''
        if rid not in seen:
            part = doc.part.related_parts.get(rid)
            image = _as_sendable(getattr(part, 'blob', b'') or b'')
            if image is None:
                seen[rid] = '[Picture unreadable]'
            elif image == 'tiny':
                seen[rid] = ''
            elif len(pictures) >= MAX_DOCX_FIGURES:
                seen[rid] = '[Picture unreadable]'
            else:
                pictures.append(image)
                seen[rid] = f'[Picture {len(pictures)}]'
        return seen[rid]

    def paragraph(p) -> str:
        out = []
        for node in p.iter():
            if node.tag in (t, mt):
                out.append(node.text or '')
            elif node.tag == tab:
                out.append('\t')
            elif node.tag in (br, cr):
                out.append('\n')
            elif node.tag == blip:
                out.append(f' {figure(node.get(embed))} ')
            elif node.tag == vml_image:
                out.append(f' {figure(node.get(qn("r:id")))} ')
        return ''.join(out).strip()

    lines = []
    for block in doc.element.body.iterchildren():
        if block.tag == qn('w:p'):
            lines.append(paragraph(block))
        elif block.tag == qn('w:tbl'):
            for row in block.iter(qn('w:tr')):
                cells = [' '.join(filter(None, (paragraph(p) for p in cell.iter(qn('w:p')))))
                         for cell in row.iter(qn('w:tc'))]
                lines.append('\t'.join(c for c in cells if c))
    text = '\n'.join(line for line in lines if line).strip()
    return text[:MAX_DOCX_CHARS], pictures


def _as_sendable(blob: bytes):
    """A picture as (bytes, type) the model reads, "tiny" for a bullet or
    logo, or None for one it cannot read (a Windows metafile, as old
    equation and ChemDraw objects are stored)."""
    if len(blob) < MIN_FIGURE_BYTES:
        return 'tiny'
    mime = image_type(blob)
    if mime in ('image/jpeg', 'image/png', 'image/webp'):
        return blob, mime
    if blob[:6] in (b'GIF87a', b'GIF89a') or blob[:2] in (b'BM',) or blob[:4] in (b'II*\x00', b'MM\x00*'):
        import io
        from PIL import Image
        try:
            out = io.BytesIO()
            Image.open(io.BytesIO(blob)).convert('RGB').save(out, 'PNG')
            return out.getvalue(), 'image/png'
        except Exception:  # noqa: BLE001
            return None
    return None


__all__ = ['NoProblemInPhoto', 'NotAnImage', 'PracticeUnavailable', 'image_type', 'max_bytes', 'read_problems']
