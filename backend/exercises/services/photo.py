"""A photographed problem, read into text for the student to check.

One request reads the photo; the photo itself is not kept. Maths comes back
in LaTeX ($...$ inline, $$...$$ on its own line) so the page can show it as it
was printed and the student can compare; a figure or table is described in
square brackets. The text is only a draft: the student corrects it and then
creates the problem from it as from any typed problem (problems.own_rubric),
so a misread digit never reaches the rubric unseen.
"""
from django.conf import settings
from django.utils.translation import gettext as _

from .common import PracticeUnavailable, ask

DEFAULT_MAX_BYTES = 8 * 1024 * 1024
MAX_TEXT_CHARS = 4000

PROMPT = """This photo should show a problem a student wants to practise (homework, a textbook or
exam question). Copy the problem out as text, exactly and completely, in the language it is
written in.

- Copy every given: numbers, units, conditions, the question itself. Do not solve it and do
  not add anything that is not in the photo.
- Write all mathematics in LaTeX: inline as $...$, a formula on its own line as $$...$$
  (fractions \\frac{a}{b}, roots \\sqrt{x}, powers x^{2}, indices x_{1}, integrals, sums,
  matrices with \\begin{pmatrix}...\\end{pmatrix}). Chemical formulas likewise ($H_2SO_4$).
- Describe any figure, graph, diagram or table in square brackets with the values it shows,
  e.g. [Right triangle ABC, right angle at C, AC = 3 cm, BC = 4 cm].
- If part of the photo cannot be read, write [unreadable] there rather than guessing.

If there is no problem in the photo (a selfie, a blank page, notes with no question), return
{"found": false, "text": ""}. Otherwise return {"found": true, "text": "..."}.

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


def read_problem(data: bytes) -> str:
    """The problem in the photo as text, maths in LaTeX."""
    mime = image_type(data)
    if mime is None:
        raise NotAnImage(_('That file is not a photo. Use a JPEG, PNG, WEBP or HEIC image.'))
    reply = ask(PROMPT, images=[(data, mime)])
    text = str(reply.get('text') or '').strip()[:MAX_TEXT_CHARS]
    if reply.get('found') is False or not text:
        raise NoProblemInPhoto(_('No problem could be found in this photo. Try a closer, sharper photo of it.'))
    return text


__all__ = ['NoProblemInPhoto', 'NotAnImage', 'PracticeUnavailable', 'image_type', 'max_bytes', 'read_problem']
