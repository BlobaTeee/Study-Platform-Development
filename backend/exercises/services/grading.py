"""Grading an attempt against the rubric, hints, and the problem's status.

Submit reports the checkpoints reached and the first step that goes wrong,
with one error type from the shared vocabulary. Hint gives one guiding
question for the step the student is stuck at; a hint that gives away the
model solution is replaced by one built from the next checkpoint.
"""
import re
import unicodedata
from datetime import timedelta

from django.utils import timezone

from ml_pipeline.language import language_name
from notebooks.services.units import unit_symbols
from notebooks.services.writing_style import WRITING_STYLE, tidy_prose

from ..models import Exercise, ExerciseAttempt
from .problems import answer_format, answer_kind
from .common import ERROR_LIST, ERROR_TYPES, ask, language_of

REVEAL_AFTER = 3          # failed submits in a round before the solution unlocks
REVISIT_DAYS = 3
LEAK_WORDS = 5            # this many words in a row from the solution is giving it away


def problem_language(exercise: Exercise) -> str:
    return (exercise.reference or {}).get('language') or language_of(exercise.prompt)


def round_attempts(exercise: Exercise):
    return exercise.attempts.filter(created_at__gte=exercise.round_started_at)


def start_due_revisit(exercise: Exercise) -> None:
    """A problem due again starts a fresh round: earlier attempts stay in the
    record, but the solution is hidden until it is solved again."""
    if exercise.status == 'revisit' and exercise.revisit_on and exercise.revisit_on <= timezone.localdate():
        exercise.status = 'new'
        exercise.revisit_on = None
        exercise.round_started_at = timezone.now()
        exercise.save(update_fields=['status', 'revisit_on', 'round_started_at'])


def solution_open(exercise: Exercise) -> bool:
    """Whether the rubric may be shown: solved, or unlocked, in this round."""
    if exercise.status == 'mastered':
        return True
    for attempt in round_attempts(exercise):
        if attempt.kind == 'reveal' or (attempt.kind == 'submit' and attempt.result.get('verdict') == 'passed'):
            return True
    return False


def failed_submits(exercise: Exercise) -> int:
    return sum(1 for a in round_attempts(exercise)
               if a.kind == 'submit' and a.result.get('verdict') != 'passed')


def _numbered(steps: list[str]) -> str:
    return '\n'.join(f'Sentence {i}: {s}' for i, s in enumerate(steps, 1)) or '(nothing written yet)'


def _format_note(answer_format: str) -> str:
    """How to read the attempt: the student's own text, cut into sentences."""
    note = ("\nThe attempt is the student's own answer, cut into numbered sentences. One step of their "
            'reasoning may run over several sentences, or one sentence hold several steps: wherever this '
            'asks about a step, give the number of the sentence where it is written.')
    if answer_format == 'points':
        note += (' The answer is a set of separate reasons or arguments (explain, compare, justify), not '
                 'working in order.')
    return note + '\n'


def _rubric(exercise: Exercise) -> tuple[str, str]:
    ref = exercise.reference or {}
    checkpoints = '\n'.join(f'[{c["id"]}] {c["text"]}' for c in ref.get('checkpoints', []))
    solution = '\n'.join(f'{i}. {s}' for i, s in enumerate(ref.get('solution', []), 1))
    return checkpoints, solution


def submit(exercise: Exercise, steps: list[str], text: str = '') -> ExerciseAttempt:
    """`steps` are the answer's sentences; `text` the answer as written, kept
    so the page can give it back exactly as the student wrote it."""
    result = grade(exercise, steps)
    attempt = ExerciseAttempt.objects.create(exercise=exercise, kind='submit', steps=steps,
                                             result={**result, 'text': text} if text else result)
    if result['verdict'] == 'passed':
        _settle(exercise, first_try=failed_submits(exercise) == 0 and not _revealed(exercise))
    return attempt


def grade(exercise: Exercise, steps: list[str], quick: bool = True) -> dict:
    """The grade alone, with nothing saved: `exercise` may be unsaved, which
    is how the grader is measured on ProcessBench.

    `quick` puts it on the fast lane, for a student waiting on one answer. A
    mock test's written answer passes False: it is marked once, at submit,
    and a lane that gives up after a few seconds would cost its points."""
    checkpoints, solution = _rubric(exercise)
    lang = problem_language(exercise)
    prompt = f"""Grade a student's attempt at a practice problem. Write in {language_name(lang)}.

Check the attempt against the checkpoints, not the model solution's wording: a different
valid method that reaches a checkpoint has reached it. The model solution is for you only;
never quote it.

A short answer is not a wrong one. Do not flag a step for being brief, for skipping working
the student plainly got right, or for using a known rule or formula without deriving it.
Report something as missing only when a checkpoint is not reached at all.
A sentence that is true but not needed (background, a side remark, an extra fact) is not a
mistake either: never flag it. Flag only what is actually wrong.

- "met": the ids of the checkpoints the attempt reaches correctly.
- "first_wrong_step": the number of the first step that contains a mistake itself (a wrong
  statement, calculation, rule or conclusion).
  A right step that is followed by a wrong one is not the wrong step.
  Point at the step where the mistake is written. If a needed step
  was skipped, give the number of the step written in its place; if the attempt stops
  short, the number after its last step. null only if every checkpoint is met and no step
  is wrong.
- "wrong_step_quote": that step's text copied exactly, or "" if the attempt stops short.
- "error_type": for that step, one of:
{ERROR_LIST}
  Choose by what went wrong: "misread" when the step contradicts something the problem
  states; "unsupported" when each fact used is right but the conclusion does not follow from
  them; "concept" only when the rule, definition or principle itself is wrong.
- "detail": one sentence, specific to this step and this subject, saying what is wrong.
- "hint": one question that would help the student fix that step without giving the answer.

Problem:
{exercise.prompt}

Checkpoints:
{checkpoints}

Model solution (do not reveal):
{solution}

Student's attempt:
{_numbered(steps)}
{_format_note(answer_format(exercise))}
{WRITING_STYLE}

Return ONLY valid JSON:
{{"met": [1], "first_wrong_step": 2, "wrong_step_quote": "...", "error_type": "concept", "detail": "...", "hint": "..."}}"""

    return clean_grade(ask(prompt, quick=quick), exercise, steps)


def clean_grade(data: dict, exercise: Exercise, steps: list[str]) -> dict:
    """The grader's reply in a shape the page can trust.

    Passed means every checkpoint met and no step flagged. A reply that says
    a checkpoint is missing but names no step is read as stopping short."""
    ids = {c['id'] for c in (exercise.reference or {}).get('checkpoints', [])}
    met = sorted({m for m in (data.get('met') or []) if isinstance(m, int) and not isinstance(m, bool) and m in ids}) \
        if isinstance(data.get('met'), list) else []
    wrong = data.get('first_wrong_step')
    wrong = wrong if isinstance(wrong, int) and not isinstance(wrong, bool) and 1 <= wrong <= len(steps) + 1 else None
    if not steps:
        wrong = 1
    passed = set(met) == ids and wrong is None
    if passed:
        return {'verdict': 'passed', 'met': met, 'first_wrong_step': None, 'error_type': None,
                'detail': '', 'hint': ''}
    if wrong is None:
        wrong = len(steps) + 1
    # Graders tend to name the right step in words and number it off by one;
    # the step they quote is the one to trust.
    quote = str(data.get('wrong_step_quote') or '').strip()[:400]   # verbatim, to match the step
    quoted = _step_quoted(quote, steps)
    if quoted is not None:
        wrong = quoted
    error_type = data.get('error_type') if data.get('error_type') in ERROR_TYPES else 'missing_step'
    hint = tidy_prose(str(data.get('hint') or ''))[:400]
    if leaks(hint, exercise):
        hint = fallback_hint(exercise, met)
    return {'verdict': 'needs_work', 'met': met, 'first_wrong_step': wrong, 'error_type': error_type,
            'detail': tidy_prose(str(data.get('detail') or ''))[:400], 'hint': hint,
            # What the grader quoted and the step it matched (None: no match),
            # kept so an evaluation can see whether the quote did its job.
            'quote': quote, 'quote_step': quoted}


def _step_quoted(quote, steps: list[str]) -> int | None:
    """The 1-based step a quote was copied from, or None if it matches none."""
    norm = lambda t: ' '.join(_WORD.findall(str(t).lower()))
    q = norm(quote or '')
    if len(q) < 8:
        return None
    hits = [i for i, step in enumerate(steps, 1) if q in norm(step) or (len(norm(step)) >= 8 and norm(step) in q)]
    return hits[0] if len(hits) == 1 else None


def hint(exercise: Exercise, steps: list[str], text: str = '') -> ExerciseAttempt:
    checkpoints, solution = _rubric(exercise)
    lang = problem_language(exercise)
    prompt = f"""A student is stuck on a practice problem and asked for a hint. Write in {language_name(lang)}.

Give ONE short question that points them to the next thing to work out, given the steps
they have so far. Do not state the next step, a result, or any part of the model solution.
If a step they wrote is wrong, point at that step instead.

Problem:
{exercise.prompt}

Checkpoints:
{checkpoints}

Model solution (do not reveal):
{solution}

Student's steps so far:
{_numbered(steps)}
{_format_note(answer_format(exercise))}
{WRITING_STYLE}

Return ONLY valid JSON: {{"hint": "..."}}"""

    hint_text = tidy_prose(str(ask(prompt, quick=True).get('hint') or ''))[:400]
    if not hint_text or leaks(hint_text, exercise):
        hint_text = fallback_hint(exercise, [])
    result = {'hint': hint_text, 'text': text} if text else {'hint': hint_text}
    return ExerciseAttempt.objects.create(exercise=exercise, kind='hint', steps=steps, result=result)


def check(exercise: Exercise, given) -> ExerciseAttempt:
    """A choice, true/false or short answer checked against its key, with
    no model request. `given` is the label picked, {label: bool} for each
    statement, or the text typed."""
    ref = exercise.reference or {}
    kind = answer_kind(exercise)
    if kind == 'choice':
        right = str(given or '').strip().lower() == str(ref.get('answer', '')).lower()
        result = {'answer': str(given or '').strip()}
    elif kind == 'true_false':
        marks = given if isinstance(given, dict) else {}
        statements = ref.get('statements', [])
        correct = sum(1 for st in statements if marks.get(st['label']) is st['answer'])
        right = correct == len(statements)
        result = {'answers': {st['label']: marks.get(st['label']) for st in statements},
                  'correct': correct, 'total': len(statements)}
    else:
        text = str(given or '').strip()
        right = short_matches(text, [ref.get('answer', ''), *ref.get('accept', [])])
        result = {'text': text}
    result = {'kind': kind, 'verdict': 'passed' if right else 'needs_work',
              'error_type': None if right else 'wrong_answer', **result}
    attempt = ExerciseAttempt.objects.create(exercise=exercise, kind='submit', steps=[], result=result)
    if right:
        _settle(exercise, first_try=failed_submits(exercise) == 0 and not _revealed(exercise))
    return attempt


_NUMBER = re.compile(r'^[-+]?\d+(?:[.,]\d+)?$')


def short_matches(given: str, answers: list[str]) -> bool:
    """Whether a short answer is one of the accepted ones: numbers by value
    (a decimal comma or point, spaces and a trailing stop do not matter),
    words ignoring case, spaces and surrounding $."""
    def norm(value):
        value = unit_symbols(unicodedata.normalize('NFC', str(value or ''))).strip().strip('$').strip().rstrip('.')
        return re.sub(r'\s+', '', value.lower())
    mine = norm(given)
    if not mine:
        return False
    for answer in answers:
        theirs = norm(answer)
        if not theirs:
            continue
        if _NUMBER.match(mine) and _NUMBER.match(theirs):
            a, b = float(mine.replace(',', '.')), float(theirs.replace(',', '.'))
            if abs(a - b) <= 1e-9 * max(1.0, abs(b)):
                return True
        elif mine == theirs:
            return True
    return False


def reveal(exercise: Exercise) -> ExerciseAttempt:
    attempt = ExerciseAttempt.objects.create(exercise=exercise, kind='reveal', steps=[], result={})
    _settle(exercise, first_try=False)
    return attempt


def _revealed(exercise: Exercise) -> bool:
    return round_attempts(exercise).filter(kind='reveal').exists()


def _settle(exercise: Exercise, first_try: bool) -> None:
    """Solved first time is mastered; anything else comes back in a few days."""
    if first_try:
        exercise.status, exercise.revisit_on = 'mastered', None
    elif exercise.status != 'mastered':
        exercise.status, exercise.revisit_on = 'revisit', timezone.localdate() + timedelta(days=REVISIT_DAYS)
    exercise.save(update_fields=['status', 'revisit_on'])


_WORD = re.compile(r'\w+', re.UNICODE)


def leaks(text: str, exercise: Exercise) -> bool:
    """Whether `text` gives the model solution away: a run of words lifted
    from it, or a number it reaches that the problem never gave."""
    if not text:
        return False
    words = [w.lower() for w in _WORD.findall(text)]
    runs = {tuple(words[i:i + LEAK_WORDS]) for i in range(len(words) - LEAK_WORDS + 1)}
    given = set(re.findall(r'\d+(?:[.,]\d+)?', exercise.prompt))
    ref = exercise.reference or {}
    # A short answer is given away by its value just as by a solution step.
    key = [str(ref['answer'])] if answer_kind(exercise) == 'short' and ref.get('answer') else []
    for step in [*ref.get('solution', []), *key]:
        sw = [w.lower() for w in _WORD.findall(step)]
        if runs & {tuple(sw[i:i + LEAK_WORDS]) for i in range(len(sw) - LEAK_WORDS + 1)}:
            return True
        for number in re.findall(r'\d+(?:[.,]\d+)?', step):
            if number not in given and re.search(rf'(?<![\d.,]){re.escape(number)}(?![\d]|[.,]\d)', text):
                return True
    return False


def fallback_hint(exercise: Exercise, met: list[int]) -> str:
    """A hint with no model: the first checkpoint not reached, as a question."""
    pending = [c for c in (exercise.reference or {}).get('checkpoints', []) if c['id'] not in set(met)]
    target = pending[0]['text'] if pending else ''
    # Vietnamese only on its own marks: on a short English prompt the word
    # lists can tip the other way.
    marked = any(unicodedata.combining(c) for c in unicodedata.normalize('NFD', exercise.prompt)) \
        or 'đ' in exercise.prompt.lower()
    if marked and language_of(exercise.prompt) == 'vi':
        return f'Bài làm của bạn đã có ý này chưa: {target.rstrip(".")}?' if target else 'Đọc lại đề: đề hỏi chính xác điều gì?'
    return f'Does your answer establish this yet: {target.rstrip(".")}?' if target else 'Read the problem again: what exactly does it ask?'


def mistakes_by_notebook(user) -> list[dict]:
    """Errors made on submit, counted by type per notebook (own problems on a
    line of their own, notebook None), most first."""
    out: dict[int | None, dict] = {}
    attempts = (ExerciseAttempt.objects.filter(exercise__user=user, kind='submit', result__verdict='needs_work')
                .select_related('exercise__notebook'))
    for a in attempts:
        nb = a.exercise.notebook
        # The student's own problems have no notebook; they share one line.
        key, title = (nb.id, nb.title) if nb else (None, '')
        entry = out.setdefault(key, {'notebook_id': key, 'title': title, 'total': 0, 'types': {}})
        kind = a.result.get('error_type') or 'missing_step'
        slot = entry['types'].setdefault(kind, {'type': kind, 'count': 0, 'exercise_ids': []})
        slot['count'] += 1
        if a.exercise_id not in slot['exercise_ids']:
            slot['exercise_ids'].append(a.exercise_id)
        entry['total'] += 1
    result = []
    for entry in sorted(out.values(), key=lambda e: -e['total']):
        entry['types'] = sorted(entry['types'].values(), key=lambda t: -t['count'])
        result.append(entry)
    return result
