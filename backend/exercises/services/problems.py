"""Writing practice problems and their hidden rubric.

A problem from a document makes the student apply what the document says to
a case it does not spell out. The rubric is written in the same request: a
model solution, the checkpoints any correct answer must reach, and the
mistakes a student is likely to make. Each checkpoint quotes the document;
one whose quote is not in the text is dropped, so a rubric cannot rest on
something the student was never given.
"""
import re
import unicodedata

from django.utils.translation import gettext as _

from ml_pipeline.language import language_name
from notebooks.services.key_points import _find, _searchable
from notebooks.services.units import unit_symbols
from notebooks.services.writing_style import WRITING_STYLE, tidy_prose

from ..models import Exercise
from .common import ERROR_LIST, ERROR_TYPES, PracticeUnavailable, ask, items_of, language_of, printed_answer

PER_DOCUMENT = 3
MIN_CHECKPOINTS = 2
MAX_CHECKPOINTS = 6
MAX_MATERIAL_CHARS = 14000
MIN_OWN_CHARS = 15
MAX_OWN_CHARS = 4000
DIFFICULTY_ORDER = {'easy': 0, 'medium': 1, 'hard': 2}
#: How the student writes the answer: "steps" for working that runs in order
#: (a calculation, a proof, a procedure, code), "points" for separate reasons or
#: arguments (explain, compare, justify, evaluate). Problems saved before this
#: field existed are steps.
ANSWER_FORMATS = ('steps', 'points')
DEFAULT_FORMAT = 'steps'
#: How the answer is given. "written" is free text graded by the model;
#: the other three carry an answer key and are checked without a request.
#: Problems written from a document, and any saved before this field, are
#: written.
ANSWER_KINDS = ('written', 'choice', 'true_false', 'short')
KEYED_KINDS = ('choice', 'true_false', 'short')
MAX_OPTIONS = 8
MAX_SHORT_ANSWER = 80

RUBRIC_SHAPE = (
    '"format": "steps|points", '
    '"solution": ["step 1", "step 2", ...], '
    '"checkpoints": [{"text": "what a correct answer must establish", "basis": "exact quote"}], '
    '"mistakes": [{"text": "a likely wrong move", "type": "one error type"}]'
)

ANSWER_FORMAT_RULE = """- "format": how the student writes the answer. "steps" when it is working that runs in order (a
  calculation, a proof, a procedure, a piece of code); "points" when it is a set of separate reasons
  or arguments (explain, compare, justify, evaluate, propose)."""

RUBRIC_RULES = f"""For each problem also write its rubric, which the student never sees until they solve it:
{ANSWER_FORMAT_RULE}
- "solution": a model solution as short numbered steps (or points, for a "points" problem).
- "checkpoints": {MIN_CHECKPOINTS} to {MAX_CHECKPOINTS} things ANY correct answer must establish,
  whatever route it takes (a result, a decision, a justification), not wording to match.
- "mistakes": 2 to 4 likely wrong moves, each with one error type from this list:
{ERROR_LIST}
- Inside LaTeX ($...$), put any word in \\text{{...}}, e.g. $V = \\text{{dài}} \\cdot \\text{{rộng}}$;
  better still, keep words outside the maths.
- Write a chemical formula or equation in \\ce{{...}} inside the maths, so it prints upright:
  $\\ce{{H2SO4}}$, $\\ce{{Zn + Cu^2+ -> Zn^2+ + Cu}}$; keep one the problem already writes that way."""


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
    # Problems are written from the main ideas. A document never read for
    # them (its reading failed at upload) is read now, once, and keeps them:
    # its opening alone is often a table of contents (a scanned book, 2026-11-24).
    from notebooks.services.key_points import ensure_key_points
    ensure_key_points(source)
    prompt = f"""Write {PER_DOCUMENT} practice problems from this study material, in {language_name(lang)}:
one easy, one medium, one hard.

First work out which subject the material belongs to. Then give each problem a DIFFERENT
kind of task that people in that subject really do, for example:
- mathematics, statistics: a value to compute, a result to prove, a quantity to estimate
- physics, chemistry, biology: predict or explain an outcome, design or read an experiment, a calculation
- geography, history, social studies: explain a pattern from data the problem gives (a table,
  figures, a described map), compare two places or periods, weigh causes and effects
- technology, engineering, computing: design a process or a solution, find the cause of a fault,
  choose between options and justify it, write or fix code
- law, economics, business: analyse a case and reach a decision
- languages, literature: translate, correct or analyse a passage
Do not make all three problems calculations unless the material is only about calculating.

Each problem makes the student APPLY the ideas to a situation the material does not
describe word for word. Never a recall question ("What is ...?", "Define ..."). The
problem gives every fact and number of the case itself; what the material teaches (rules,
values, definitions) is what the student brings, so do not restate it in the problem.

{RUBRIC_RULES}
- Each checkpoint has a "basis": an exact quote from the material (one phrase or sentence, at
  least five words) that the checkpoint rests on, copied character for character.

Material ("{source.title}"):
{material_of(source)}

{WRITING_STYLE}

Return ONLY valid JSON:
{{"subject": "...", "problems": [{{"prompt": "...", "difficulty": "easy|medium|hard", {RUBRIC_SHAPE}}}]}}"""

    raw = items_of(ask(prompt, typed=False), 'problems')
    problems = [p for p in (_problem(item, text, source.title, lang) for item in raw) if p][:PER_DOCUMENT]
    if not problems:
        raise PracticeUnavailable(_('No usable problem came back for this document. Try again.'))
    problems.sort(key=lambda p: DIFFICULTY_ORDER[p['difficulty']])
    return [Exercise.objects.create(user=user, notebook=source.notebook, source=source, origin='document', **p)
            for p in problems]


def own_problem(user, text: str) -> Exercise:
    """The student's own problem: checked for being solvable, then given a
    rubric. Its checkpoints rest on general knowledge, not a document, so it
    belongs to no notebook."""
    problem = own_rubric(text)
    return Exercise.objects.create(user=user, notebook=None, source=None, origin='own', **problem)


KIND_RULES = """- "kind": how the student answers. "choice" when the problem gives answer options and asks
  for one (A, B, C, D...); "true_false" when it gives statements to mark true or false one by one;
  "short" when it, or its instruction, asks only for a final value or a few words and no working;
  "written" for everything else (working, explanations, essays).
- For "choice": "prompt" is the question WITHOUT its options; "options": [{"label": "A", "text": "..."}]
  copied exactly as given and in order; "answer": the label of the correct option.
- For "true_false": "prompt" is the shared stem WITHOUT the statements; "statements":
  [{"label": "a", "text": "...", "answer": true}] copied exactly, each with whether it is true.
- For "short": "answer": the final value or words, as short as possible; "accept": other ways of
  writing the same answer, if any.
- Keep all mathematics exactly as the problem writes it, in LaTeX between $...$, in the prompt,
  the options and the statements alike.
- Write "solution" and "checkpoints" for every kind: they explain why the answer is right."""

KIND_SHAPE = ('"kind": "written|choice|true_false|short", "options": [], "statements": [], '
              '"answer": "", "accept": [], ')


def own_rubric(text: str) -> dict:
    """The prompt, difficulty and rubric for a problem the student brought,
    without saving anything (the grader's evaluation uses this too)."""
    lang = language_of(text)
    prompt = f"""A student brought their own problem to practise on. Work in {language_name(lang)}.

First decide whether it can be solved as written. If a needed fact, number or condition is
missing, or it is not a problem at all, return {{"complete": false, "missing": "what is missing, one sentence"}}.

Otherwise return the problem tidied (fix typos only, keep its meaning, every given and its line
breaks; a table stays a Markdown table, one row per line),
its difficulty, how it is answered, and its rubric.

{KIND_RULES}
{RUBRIC_RULES}
- Leave each checkpoint's "basis" empty.

Problem:
{text}

{WRITING_STYLE}

Return ONLY valid JSON, either the refusal above or:
{{"complete": true, "prompt": "...", "difficulty": "easy|medium|hard", {KIND_SHAPE}{RUBRIC_SHAPE}}}"""

    data = ask(prompt)
    if data.get('complete') is False:
        missing = tidy_prose(str(data.get('missing') or ''))
        raise IncompleteProblem(missing or _('Something the problem needs is missing.'))
    problem = _problem({**data, 'prompt': data.get('prompt') or text}, None, '', lang, original=text)
    if not problem:
        raise PracticeUnavailable(_('A rubric could not be written for this problem. Try again.'))
    return problem


class IncompleteProblem(Exception):
    pass


#: Most problems picked together from one photo or file, and how many go in
#: one request: five answer keys in one reply ran past 30 s on 2026-11-23, so three
#: go together, each request with the long deadline. Twenty is seven requests
#: side by side; a whole 30-question exam would be ten, which the free tier's
#: per-minute limit turns away.
MAX_SET = 20
SET_PER_REQUEST = 3


def own_set(user, texts: list[str], figures: list[list] | None = None,
            title: str = '', answers: list | None = None,
            hints: list | None = None) -> tuple[list[Exercise], list[dict]]:
    """Several problems from one photo or file, made in as few requests as
    possible and kept together under one set key, in the order given.

    Returns the problems made and the ones skipped, each skipped one as
    {"index", "reason"} (0-based, with what is missing when that is why).
    When none could be made: IncompleteProblem if the model found them
    unsolvable, PracticeUnavailable if it could not be asked. answers[i] is
    problem i's answer as the paper prints it (common.printed_answer), or None:
    the key then follows the paper, not the model. hints[i] is the key as
    the model read it from a picture: it may be misread, so the model is told
    of it but solves the problem itself."""
    import uuid
    from concurrent.futures import ThreadPoolExecutor

    texts = [t.strip()[:MAX_OWN_CHARS] for t in texts][:MAX_SET]
    figures = figures or []
    answers = [printed_answer(a) for a in (answers or [])]
    answers += [None] * (len(texts) - len(answers))
    hints = [printed_answer(h) for h in (hints or [])]
    hints += [None] * (len(texts) - len(hints))
    chunks = [list(range(i, min(i + SET_PER_REQUEST, len(texts)))) for i in range(0, len(texts), SET_PER_REQUEST)]

    def rubrics(indexes):
        try:
            return indexes, _set_rubrics([texts[i] for i in indexes],
                                         [figures[i] if i < len(figures) else [] for i in indexes],
                                         [answers[i] for i in indexes], [hints[i] for i in indexes]), ''
        except PracticeUnavailable as exc:
            return indexes, [], str(exc)

    with ThreadPoolExecutor(max_workers=max(1, len(chunks))) as pool:
        replies = list(pool.map(rubrics, chunks))

    made: dict[int, dict] = {}
    skipped: list[dict] = []
    failure = ''
    for indexes, items, error in replies:
        failure = failure or error
        for position, i in enumerate(indexes):
            item = items[position] if position < len(items) and isinstance(items[position], dict) else None
            if item is None:
                skipped.append({'index': i, 'reason': error or _('No answer key came back for this one.')})
            elif item.get('complete') is False:
                missing = tidy_prose(str(item.get('missing') or ''))
                skipped.append({'index': i, 'reason': missing or _('Something the problem needs is missing.')})
            else:
                item = _with_printed_answer(item, answers[i])
                problem = _problem({**item, 'prompt': item.get('prompt') or texts[i]}, None, '',
                                   language_of(texts[i]), original=texts[i])
                if problem:
                    if answers[i] is not None and problem['reference'].get('kind') != 'written':
                        problem['reference']['answer_from'] = 'paper'
                    made[i] = problem
                else:
                    skipped.append({'index': i, 'reason': _('No answer key came back for this one.')})
    if not made:
        if failure:
            raise PracticeUnavailable(failure)
        # Every problem was looked at and none can be solved as written: say why.
        raise IncompleteProblem(skipped[0]['reason'] if skipped else _('Something the problem needs is missing.'))
    key = uuid.uuid4().hex
    title = (title or '').strip()[:200]
    exercises = [Exercise.objects.create(user=user, notebook=None, source=None, origin='own', set_key=key,
                                         set_title=title,
                                         figures=figures[i] if i < len(figures) else [], **made[i])
                 for i in sorted(made)]
    return exercises, sorted(skipped, key=lambda s: s['index'])


def _with_printed_answer(item: dict, printed) -> dict:
    """The model's answer key with the paper's own answer in its place. The
    model solves most problems right but not all (on 2026-11-23 it marked a
    statement true that the paper's key marks false); the paper is the
    authority. A printed answer that does not fit the kind is left out."""
    if printed is None:
        return item
    kind = str(item.get('kind') or '').lower()
    if kind == 'choice' and isinstance(printed, str) and len(printed) == 1 and printed.isalpha():
        return {**item, 'answer': printed.upper()}
    if kind == 'true_false' and isinstance(printed, dict) and isinstance(item.get('statements'), list):
        statements = [{**st, 'answer': printed[_label(st.get('label')).lower()]}
                      if isinstance(st, dict) and _label(st.get('label')).lower() in printed else st
                      for st in item['statements']]
        return {**item, 'statements': statements}
    if kind == 'short' and isinstance(printed, str):
        from .grading import short_matches
        same = short_matches(str(item.get('answer') or ''), [printed])
        return {**item, 'answer': printed, 'accept': item.get('accept') if same else []}
    return item


def _as_words(printed) -> str:
    if isinstance(printed, dict):
        return ', '.join(f'{label} {"true" if mark else "false"}' for label, mark in printed.items())
    return str(printed)


def _set_rubrics(texts: list[str], figures: list[list] | None = None, answers: list | None = None,
                 hints: list | None = None) -> list:
    """One request for several problems; the reply's list is in their order.
    The figures cut from the page go along as pictures: a description such as
    "open-chain structural formula of a carbohydrate" does not say which one,
    and a problem that needs to know was skipped as incomplete."""
    from . import figures as cut_figures
    lang = language_of('\n'.join(texts)[:3000])
    numbered = '\n\n'.join(f'Problem {n}:\n{text}' for n, text in enumerate(texts, 1))
    images, legend = [], []
    for n, cut in enumerate(figures or [], 1):
        tagged = cut_figures.tags_in(texts[n - 1]) if n <= len(texts) else set()
        for m, url in enumerate(cut or [], 1):
            # Only a figure the problem's text points at: another is no part of it.
            image = cut_figures.image_of(url) if m in tagged else None
            if image:
                images.append(image)
                legend.append(f'picture {len(images)} is Problem {n}\'s Figure {m}')
    printed = [f'Problem {n}: {_as_words(a)}' for n, a in enumerate(answers or [], 1) if a is not None]
    keyed = (f"""The paper's own answer key gives: {'; '.join(printed)}. Take these as the right answers:
give them as the answer, and write the solution and checkpoints that reach them.
""" if printed else '')
    read = [f'Problem {n}: {_as_words(h)}' for n, h in enumerate(hints or [], 1)
            if h is not None and (not answers or n > len(answers) or answers[n - 1] is None)]
    if read:
        keyed += f"""An answer key read from a picture of the paper suggests: {'; '.join(read)}. It may be
misread: solve each of these yourself, and where your working disagrees with it, give your own answer.
"""
    pictures = (f"""The figures cut from the page are attached as pictures, in order: {'; '.join(legend)}.
Read each of these figures from its picture; its description only names it. A figure you have as
a picture never makes a problem incomplete.
""" if images else '')
    prompt = f"""A student brought {len(texts)} problems to practise on. Work in {language_name(lang)}.

Treat each problem on its own. A figure is given as [Figure n: what it shows]: solve from its
picture when it is attached, from that description otherwise, and keep each such tag exactly as
written, where it stands, in the "prompt" you give back.
{pictures}{keyed}For each, first decide whether it can be solved as written. If a needed
fact, number or condition is missing, or it is not a problem at all, give {{"complete": false, "missing":
"what is missing, one sentence"}} for it. Otherwise give the problem tidied (fix typos only, keep its
meaning, every given and its line breaks; a table stays a Markdown table, one row per line), its
difficulty, how it is answered, and its rubric.

{KIND_RULES}
{RUBRIC_RULES}
- Leave each checkpoint's "basis" empty.

{numbered}

{WRITING_STYLE}

Return ONLY valid JSON with exactly one entry per problem, in the same order:
{{"problems": [{{"complete": true, "prompt": "...", "difficulty": "easy|medium|hard", {KIND_SHAPE}{RUBRIC_SHAPE}}}]}}"""
    return items_of(ask(prompt, images=images or None, long=True), 'problems')


def _problem(item, text: str | None, title: str, lang: str, original: str = '') -> dict | None:
    """A problem the page and the grader can trust, or None.

    `text` is the document a checkpoint must quote; None for the student's
    own problem, whose checkpoints have no document to rest on. `original` is
    the problem as the student gave it: an answer key is kept only if its
    options or statements are really in it, and a problem whose key is not
    kept falls back to a written answer on the full original text."""
    if not isinstance(item, dict):
        return None
    key = _answer_key(item, original) if original else {'kind': 'written'}
    if key is None:
        key = {'kind': 'written'}
        item = {**item, 'prompt': original}
    # The student's own problem is their words: only its units are tidied.
    prompt = tidy_prose(str(item.get('prompt') or ''), source_title=title, units_only=text is None)
    if len(prompt) < (5 if key['kind'] in KEYED_KINDS else 20):
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
    answer_format = str(item.get('format') or '').lower()
    if answer_format not in ANSWER_FORMATS:
        answer_format = DEFAULT_FORMAT
    return {'prompt': prompt[:3000], 'difficulty': difficulty,
            'reference': {**key, 'format': answer_format, 'solution': solution, 'checkpoints': checkpoints[:MAX_CHECKPOINTS], 'mistakes': mistakes,
                          # The grader writes in this, not in whatever a two-word step looks like.
                          'language': lang}}


_NOT_WORD = re.compile(r'[\W_]+', re.UNICODE)


def _plain(value) -> str:
    """Letters and digits only, lower case: enough to tell whether an option
    was copied from the problem, whatever happened to spaces and LaTeX."""
    return _NOT_WORD.sub('', unit_symbols(unicodedata.normalize('NFC', str(value or ''))).lower())


def _label(value) -> str:
    return str(value or '').strip().rstrip('.):').strip()[:3]


def _answer_key(item: dict, original: str) -> dict | None:
    """The answer key of a choice, true/false or short problem, or
    {"kind": "written"}. None when the model claimed a keyed kind but its key
    cannot be trusted: an option or statement that is not in the problem, a
    duplicate label, an answer that is not one of the options."""
    kind = str(item.get('kind') or '').lower()
    flat = _plain(original)
    if kind in ('choice', 'true_false'):
        field = 'options' if kind == 'choice' else 'statements'
        rows = item.get(field) if isinstance(item.get(field), list) else []
        out, seen = [], set()
        for raw in rows[:MAX_OPTIONS + 1]:
            if not isinstance(raw, dict):
                return None
            label, body = _label(raw.get('label')), str(raw.get('text') or '').strip()
            if not label or not body or label.lower() in seen or _plain(body) not in flat:
                return None
            seen.add(label.lower())
            row = {'label': label, 'text': unit_symbols(body)[:500]}
            if kind == 'true_false':
                if not isinstance(raw.get('answer'), bool):
                    return None
                row['answer'] = raw['answer']
            out.append(row)
        if not 2 <= len(out) <= MAX_OPTIONS:
            return None
        if kind == 'true_false':
            return {'kind': kind, 'statements': out}
        answer = _label(item.get('answer'))
        match = [o['label'] for o in out if o['label'].lower() == answer.lower()]
        return {'kind': kind, 'options': out, 'answer': match[0]} if match else None
    if kind == 'short':
        answer = str(item.get('answer') or '').strip()
        if not answer or len(answer) > MAX_SHORT_ANSWER:
            return None
        accept = [str(a).strip() for a in (item.get('accept') if isinstance(item.get('accept'), list) else [])
                  if str(a or '').strip() and len(str(a)) <= MAX_SHORT_ANSWER][:5]
        return {'kind': kind, 'answer': unit_symbols(answer), 'accept': [unit_symbols(a) for a in accept]}
    return {'kind': 'written'}


def answer_kind(exercise) -> str:
    value = (exercise.reference or {}).get('kind')
    return value if value in ANSWER_KINDS else 'written'


def answer_format(exercise) -> str:
    """How the student answers this problem: "steps" or "points"."""
    value = (exercise.reference or {}).get('format')
    return value if value in ANSWER_FORMATS else DEFAULT_FORMAT
