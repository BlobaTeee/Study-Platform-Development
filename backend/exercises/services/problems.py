"""Writing practice problems and their hidden rubric.

A problem from a document makes the student apply what the document says to
a case it does not spell out. The rubric is written in the same request: a
model solution, the checkpoints any correct answer must reach, and the
mistakes a student is likely to make. Each checkpoint quotes the document;
one whose quote is not in the text is dropped, so a rubric cannot rest on
something the student was never given.
"""
from django.utils.translation import gettext as _

from ml_pipeline.language import language_name
from notebooks.services.key_points import _find, _searchable
from notebooks.services.writing_style import WRITING_STYLE, tidy_prose

from ..models import Exercise
from .common import ERROR_LIST, ERROR_TYPES, PracticeUnavailable, ask, language_of

PER_DOCUMENT = 3
MIN_CHECKPOINTS = 2
MAX_CHECKPOINTS = 6
MAX_MATERIAL_CHARS = 14000
MIN_OWN_CHARS = 15
MAX_OWN_CHARS = 4000
DIFFICULTY_ORDER = {'easy': 0, 'medium': 1, 'hard': 2}

RUBRIC_SHAPE = (
    '"solution": ["step 1", "step 2", ...], '
    '"checkpoints": [{"text": "what a correct answer must establish", "basis": "exact quote"}], '
    '"mistakes": [{"text": "a likely wrong move", "type": "one error type"}]'
)

RUBRIC_RULES = f"""For each problem also write its rubric, which the student never sees until they solve it:
- "solution": a model solution as short numbered steps.
- "checkpoints": {MIN_CHECKPOINTS} to {MAX_CHECKPOINTS} things ANY correct answer must establish,
  whatever route it takes (a result, a decision, a justification), not wording to match.
- "mistakes": 2 to 4 likely wrong moves, each with one error type from this list:
{ERROR_LIST}"""


def material_of(source) -> str:
    """What the problems are written from: the main ideas if the document has
    been read, its text otherwise."""
    points = source.key_points or []
    if points:
        ideas = '\n'.join(f'- {p.get("point", "")}\n  "{(p.get("passage") or "")[:600]}"' for p in points)
        return ideas[:MAX_MATERIAL_CHARS]
    return (source.extracted_text or '')[:MAX_MATERIAL_CHARS]


def from_document(user, source) -> list[Exercise]:
    text = source.extracted_text or ''
    if not text.strip():
        raise PracticeUnavailable(_('This document has no text to write problems from.'))
    lang = language_of(text[:3000], source.title)
    prompt = f"""Write {PER_DOCUMENT} practice problems from this study material, in {language_name(lang)}:
one easy, one medium, one hard.

Each problem makes the student APPLY the ideas to a situation the material does not
describe word for word: a case to analyse, a value to work out, code to write or fix, a
decision to justify, a sentence to translate or correct, whatever suits the subject. Never
a recall question ("What is ...?", "Define ..."). The problem gives every fact and number
of the case itself; what the material teaches (rules, values, definitions) is what the
student brings, so do not restate it in the problem.

{RUBRIC_RULES}
- Each checkpoint has a "basis": an exact quote from the material (one phrase or sentence, at
  least five words) that the checkpoint rests on, copied character for character.

Material ("{source.title}"):
{material_of(source)}

{WRITING_STYLE}

Return ONLY valid JSON:
{{"problems": [{{"prompt": "...", "difficulty": "easy|medium|hard", {RUBRIC_SHAPE}}}]}}"""

    data = ask(prompt)
    raw = data.get('problems') if isinstance(data.get('problems'), list) else []
    problems = [p for p in (_problem(item, text, source.title, lang) for item in raw) if p][:PER_DOCUMENT]
    if not problems:
        raise PracticeUnavailable(_('No usable problem came back for this document. Try again.'))
    problems.sort(key=lambda p: DIFFICULTY_ORDER[p['difficulty']])
    return [Exercise.objects.create(user=user, notebook=source.notebook, source=source, origin='document', **p)
            for p in problems]


def own_problem(user, notebook, text: str) -> Exercise:
    """The student's own problem: checked for being solvable, then given a
    rubric. Its checkpoints rest on general knowledge, not a document."""
    problem = own_rubric(text)
    return Exercise.objects.create(user=user, notebook=notebook, source=None, origin='own', **problem)


def own_rubric(text: str) -> dict:
    """The prompt, difficulty and rubric for a problem the student brought,
    without saving anything (the grader's evaluation uses this too)."""
    lang = language_of(text)
    prompt = f"""A student brought their own problem to practise on. Work in {language_name(lang)}.

First decide whether it can be solved as written. If a needed fact, number or condition is
missing, or it is not a problem at all, return {{"complete": false, "missing": "what is missing, one sentence"}}.

Otherwise return the problem tidied (fix typos only, keep its meaning and every given),
its difficulty, and its rubric.

{RUBRIC_RULES}
- Leave each checkpoint's "basis" empty.

Problem:
{text}

{WRITING_STYLE}

Return ONLY valid JSON, either the refusal above or:
{{"complete": true, "prompt": "...", "difficulty": "easy|medium|hard", {RUBRIC_SHAPE}}}"""

    data = ask(prompt)
    if data.get('complete') is False:
        missing = tidy_prose(str(data.get('missing') or ''))
        raise IncompleteProblem(missing or _('Something the problem needs is missing.'))
    problem = _problem({**data, 'prompt': data.get('prompt') or text}, None, '', lang)
    if not problem:
        raise PracticeUnavailable(_('A rubric could not be written for this problem. Try again.'))
    return problem


class IncompleteProblem(Exception):
    pass


def _problem(item, text: str | None, title: str, lang: str) -> dict | None:
    """A problem the page and the grader can trust, or None.

    `text` is the document a checkpoint must quote; None for the student's
    own problem, whose checkpoints have no document to rest on."""
    if not isinstance(item, dict):
        return None
    prompt = tidy_prose(str(item.get('prompt') or ''), source_title=title)
    if len(prompt) < 20:
        return None
    difficulty = str(item.get('difficulty') or '').lower()
    if difficulty not in DIFFICULTY_ORDER:
        difficulty = 'medium'
    solution = [tidy_prose(str(s)) for s in (item.get('solution') or []) if str(s or '').strip()][:12] \
        if isinstance(item.get('solution'), list) else []
    if not solution:
        return None

    flat = _searchable(text)[0] if text else None
    checkpoints = []
    for raw in item.get('checkpoints') if isinstance(item.get('checkpoints'), list) else []:
        if not isinstance(raw, dict):
            continue
        point = tidy_prose(str(raw.get('text') or ''))
        basis = str(raw.get('basis') or '').strip()
        if not point:
            continue
        if flat is not None and (not basis or _find(basis, flat) is None):
            continue                       # rests on nothing the student was given
        checkpoints.append({'id': len(checkpoints) + 1, 'text': point[:300], 'basis': basis[:300]})
    if len(checkpoints) < MIN_CHECKPOINTS:
        return None

    mistakes = [{'text': tidy_prose(str(m.get('text')))[:300], 'type': m.get('type')}
                for m in (item.get('mistakes') if isinstance(item.get('mistakes'), list) else [])
                if isinstance(m, dict) and str(m.get('text') or '').strip() and m.get('type') in ERROR_TYPES][:4]
    return {'prompt': prompt[:3000], 'difficulty': difficulty,
            'reference': {'solution': solution, 'checkpoints': checkpoints[:MAX_CHECKPOINTS], 'mistakes': mistakes,
                          # The grader writes in this, not in whatever a two-word step looks like.
                          'language': lang}}
