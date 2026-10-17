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
from notebooks.services.writing_style import WRITING_STYLE, tidy_prose

from ..models import Exercise, ExerciseAttempt
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
    return '\n'.join(f'Step {i}: {s}' for i, s in enumerate(steps, 1)) or '(no steps yet)'


def _rubric(exercise: Exercise) -> tuple[str, str]:
    ref = exercise.reference or {}
    checkpoints = '\n'.join(f'[{c["id"]}] {c["text"]}' for c in ref.get('checkpoints', []))
    solution = '\n'.join(f'{i}. {s}' for i, s in enumerate(ref.get('solution', []), 1))
    return checkpoints, solution


def submit(exercise: Exercise, steps: list[str]) -> ExerciseAttempt:
    result = grade(exercise, steps)
    attempt = ExerciseAttempt.objects.create(exercise=exercise, kind='submit', steps=steps, result=result)
    if result['verdict'] == 'passed':
        _settle(exercise, first_try=failed_submits(exercise) == 0 and not _revealed(exercise))
    return attempt


def grade(exercise: Exercise, steps: list[str]) -> dict:
    """The grade alone, with nothing saved: `exercise` may be unsaved, which
    is how the grader is measured on ProcessBench."""
    checkpoints, solution = _rubric(exercise)
    lang = problem_language(exercise)
    prompt = f"""Grade a student's attempt at a practice problem. Write in {language_name(lang)}.

Check the attempt against the checkpoints, not the model solution's wording: a different
valid method that reaches a checkpoint has reached it. The model solution is for you only;
never quote it.

- "met": the ids of the checkpoints the attempt reaches correctly.
- "first_wrong_step": the number of the first step that is wrong, or where something the
  answer needs is missing (if the attempt stops short, the number after its last step).
  null only if every checkpoint is met and no step is wrong.
- "error_type": for that step, one of:
{ERROR_LIST}
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

{WRITING_STYLE}

Return ONLY valid JSON:
{{"met": [1], "first_wrong_step": 2, "error_type": "concept", "detail": "...", "hint": "..."}}"""

    return clean_grade(ask(prompt), exercise, steps)


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
    error_type = data.get('error_type') if data.get('error_type') in ERROR_TYPES else 'missing_step'
    hint = tidy_prose(str(data.get('hint') or ''))[:400]
    if leaks(hint, exercise):
        hint = fallback_hint(exercise, met)
    return {'verdict': 'needs_work', 'met': met, 'first_wrong_step': wrong, 'error_type': error_type,
            'detail': tidy_prose(str(data.get('detail') or ''))[:400], 'hint': hint}


def hint(exercise: Exercise, steps: list[str]) -> ExerciseAttempt:
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

{WRITING_STYLE}

Return ONLY valid JSON: {{"hint": "..."}}"""

    text = tidy_prose(str(ask(prompt).get('hint') or ''))[:400]
    if not text or leaks(text, exercise):
        text = fallback_hint(exercise, [])
    return ExerciseAttempt.objects.create(exercise=exercise, kind='hint', steps=steps, result={'hint': text})


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
    for step in (exercise.reference or {}).get('solution', []):
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
    """Errors made on submit, counted by type per notebook, most first."""
    out: dict[int, dict] = {}
    attempts = (ExerciseAttempt.objects.filter(exercise__user=user, kind='submit', result__verdict='needs_work')
                .select_related('exercise__notebook'))
    for a in attempts:
        nb = a.exercise.notebook
        entry = out.setdefault(nb.id, {'notebook_id': nb.id, 'title': nb.title, 'total': 0, 'types': {}})
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
