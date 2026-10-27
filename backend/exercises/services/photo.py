"""A photographed problem, read into text for the student to check.

One request reads the photo, giving each question on it separately (an exam
page holds a dozen; the student picks one to practise); the photo itself is
not kept. Maths comes back in LaTeX ($...$ inline, $$...$$ on its own line) so
the page can show it as it was printed and the student can compare; a figure or table is described in
square brackets. The text is only a draft: the student corrects it and then
creates the problem from it as from any typed problem (problems.own_rubric),
so a misread digit never reaches the rubric unseen.
"""
from django.conf import settings
from django.utils.translation import gettext as _

from .common import PracticeUnavailable, ask

DEFAULT_MAX_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 4000
MAX_QUESTIONS = 30
MAX_LABEL_CHARS = 40
MAX_INSTRUCTION_CHARS = 400

PROMPT = """This photo should show problems a student wants to practise: homework, a textbook page or
an exam page. Copy each question out as text, exactly and completely, in the language it is
written in. A page with several questions gives several; a photo of one problem gives one.

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
- Write all mathematics in LaTeX: inline as $...$, a formula on its own line as $$...$$
  (fractions \\frac{a}{b}, roots \\sqrt{x}, powers x^{2}, indices x_{1}, integrals, sums,
  matrices with \\begin{pmatrix}...\\end{pmatrix}). Chemical formulas likewise ($H_2SO_4$).
- Describe any figure, graph or diagram in square brackets with the values it shows, e.g.
  [Right triangle ABC, right angle at C, AC = 3 cm, BC = 4 cm].
- Copy a table row by row in square brackets. For a variation table (bảng biến thiên), give
  for each interval between the x values the sign of y' and the direction of the arrow of y,
  with the values at its ends, e.g. [On (-\\infty; -2): y' -, y decreases from 1 to -\\infty].
  Read each sign and each arrow from the photo; do not infer them.
- If part of a question cannot be read, write [unreadable] there rather than guessing. A
  question cut off at the edge of the photo is copied as far as it goes.

If there is no problem in the photo (a selfie, a blank page, notes with no question), return
{"found": false, "questions": []}. Otherwise return
{"found": true, "questions": [{"label": "how the page numbers it, e.g. Câu 3 or Bài 2a; when the
page has parts whose numbering restarts, the part too, e.g. Phần II · Câu 1",
"instruction": "the section's instruction, or \"\"", "text": "..."}]}
in the order they appear.

Return ONLY valid JSON."""


class NoProblemInPhoto(Exception):
    pass


class NotAnImage(Exception):
    pass


def image_type(data: bytes) -> str | None:
    """The image's type from its first bytes (never from the file name)."""
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


def read_problems(data: bytes) -> list[dict]:
    """The questions in the photo, in order, as {label, instruction, text}; maths
    in LaTeX. The instruction is the section's (how to answer), shared by many."""
    mime = image_type(data)
    if mime is None:
        raise NotAnImage(_('That file is not a photo. Use a JPEG, PNG, WEBP or HEIC image.'))
    reply = ask(PROMPT, images=[(data, mime)])
    raw = reply.get('questions')
    if not isinstance(raw, list):
        raw = [{'text': reply.get('text')}]        # an older reply shape: the whole photo as one
    questions = []
    for item in raw[:MAX_QUESTIONS]:
        if not isinstance(item, dict):
            continue
        text = str(item.get('text') or '').strip()[:MAX_TEXT_CHARS]
        if text:
            label = str(item.get('label') or '').strip()[:MAX_LABEL_CHARS]
            instruction = str(item.get('instruction') or '').strip()[:MAX_INSTRUCTION_CHARS]
            questions.append({'label': label or str(len(questions) + 1), 'instruction': instruction, 'text': text})
    if reply.get('found') is False or not questions:
        raise NoProblemInPhoto(_('No problem could be found in this photo. Try a closer, sharper photo of it.'))
    return questions


__all__ = ['NoProblemInPhoto', 'NotAnImage', 'PracticeUnavailable', 'image_type', 'max_bytes', 'read_problems']
