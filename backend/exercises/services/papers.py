"""A paper the student brings (a photo or a file), read once and sat whole.

On 2026-11-26 the user moved bringing a paper from practice to mock tests:
a paper is for sitting. It is read once (photo.read_problems), then sat as
printed: timed, marked out of 10 by its answer key. No model writes a model
solution for each question up front, as practice did (seven requests for
twenty questions); only what the key does not give is asked for:

- the answers a photo has no key for, all in one request (solve_keys);
- a rubric for each written question, which is marked against it.

What is missed comes back to practice afterwards, and only then is its
model solution written, in the background (misses_to_practice), or when
the student opens the problem first (fill_pending).
"""
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from django.utils.translation import gettext as _

from . import figures as cut_figures
from .common import PracticeUnavailable, ask, language_of, printed_answer
from .photo import MAX_QUESTIONS
from .sitting import weigh

logger = logging.getLogger(__name__)

KEYED = ('choice', 'true_false', 'short')
#: Missed questions whose solution is written straight after the sitting.
BACKGROUND_FILL = 6
MAX_TEXT = 4000


def _labelled(raw, upper: bool) -> list[dict]:
    out = []
    for entry in raw if isinstance(raw, list) else []:
        if isinstance(entry, dict):
            label = str(entry.get('label') or '').strip()
            text = str(entry.get('text') or '').strip()[:MAX_TEXT]
            if len(label) == 1 and label.isalpha() and text:
                out.append({'label': label.upper() if upper else label.lower(), 'text': text})
    return out


def clean(raw) -> list[dict]:
    """The questions as the page sends them back from the reader, checked:
    nothing but what the reader gives, and no more than it reads."""
    questions = []
    for item in (raw if isinstance(raw, list) else [])[:MAX_QUESTIONS]:
        if not isinstance(item, dict):
            continue
        kind = item.get('kind') if item.get('kind') in (*KEYED, 'written') else 'written'
        q = {'label': str(item.get('label') or '').strip()[:80],
             'instruction': str(item.get('instruction') or '').strip()[:500],
             'text': str(item.get('text') or '').strip()[:MAX_TEXT], 'kind': kind,
             'options': _labelled(item.get('options'), upper=True) if kind == 'choice' else [],
             'statements': _labelled(item.get('statements'), upper=False) if kind == 'true_false' else [],
             'answer': printed_answer(item.get('answer')), 'hint': printed_answer(item.get('hint')),
             'figures': [cut_figures.clean(f) for f in (item.get('figures') or [])
                         if isinstance(item.get('figures'), list)][:cut_figures.MAX_PER_QUESTION]}
        if q['kind'] == 'choice' and len(q['options']) < 2 or q['kind'] == 'true_false' and len(q['statements']) < 2:
            q['kind'] = 'written'
        if q['text'] or q['options'] or q['statements']:
            questions.append(q)
    return questions


def fits(q: dict, key) -> bool:
    """Whether `key` answers this question as its kind is answered."""
    if key is None:
        return False
    if q['kind'] == 'choice':
        return isinstance(key, str) and key.upper() in {o['label'] for o in q['options']}
    if q['kind'] == 'true_false':
        return isinstance(key, dict) and all(isinstance(key.get(s['label']), bool) for s in q['statements'])
    if q['kind'] == 'short':
        return isinstance(key, str) and bool(key.strip())
    return False


def as_printed(q: dict) -> str:
    """The question as one text: its instruction, stem, options or statements."""
    lines = [q.get('instruction') or '', q['text']]
    lines += [f"{o['label']}. {o['text']}" for o in q.get('options') or []]
    lines += [f"{s['label']}) {s['text']}" for s in q.get('statements') or []]
    return '\n'.join(line for line in lines if line).strip()


def solve_keys(questions: list[dict]) -> dict[int, object]:
    """The answers the paper does not print, in one request: {index: key}.
    A key read off a photo is only a hint (it can be misread)."""
    numbered = []
    for n, q in enumerate(questions, 1):
        hint = f"\n(A key read from a picture of the paper suggests: {q['hint']}; it may be misread.)" \
            if q.get('hint') is not None else ''
        numbered.append(f"Problem {n} ({q['kind']}):\n{as_printed(q)}{hint}")
    prompt = f"""Solve each problem below and give only its final answer. Work carefully; do not explain.

{chr(10).join(numbered)}

Answer each as its kind is answered: "choice", the option's letter ("B"); "true_false", each
statement's mark ({{"a": true, "b": false, ...}}); "short", the final value or words as short as
possible ("-0,7"). Return ONLY valid JSON: {{"answers": [{{"n": 1, "answer": ...}}]}}"""
    reply = ask(prompt, long=True)
    out = {}
    for entry in reply.get('answers') if isinstance(reply.get('answers'), list) else []:
        if not isinstance(entry, dict):
            continue
        try:
            n = int(entry.get('n'))
        except (TypeError, ValueError):
            continue
        key = printed_answer(entry.get('answer'))
        if 1 <= n <= len(questions) and fits(questions[n - 1], key):
            out[n - 1] = key.upper() if questions[n - 1]['kind'] == 'choice' else key
    return out


def _rubrics(questions: list[dict], answers: list | None = None) -> list[dict | None]:
    """A model solution and checkpoints for each question, three to a request,
    a few requests at a time: [reference | None], in order."""
    from .problems import SET_PARALLEL, SET_PER_REQUEST, _problem, _set_rubrics, _with_printed_answer
    answers = answers or [None] * len(questions)
    chunks = [list(range(i, min(i + SET_PER_REQUEST, len(questions)))) for i in range(0, len(questions), SET_PER_REQUEST)]

    def one(indexes):
        texts = [as_printed(questions[i]) for i in indexes]
        try:
            items = _set_rubrics(texts, [questions[i].get('figures') or [] for i in indexes],
                                 [answers[i] for i in indexes])
        except PracticeUnavailable:
            return indexes, []
        made = []
        for i, item, text in zip(indexes, items + [None] * len(indexes), texts):
            if not isinstance(item, dict) or item.get('complete') is False:
                made.append(None)
                continue
            item = _with_printed_answer(item, answers[i])
            problem = _problem({**item, 'prompt': text}, None, '', language_of(text), original=text)
            made.append(problem['reference'] if problem else None)
        return indexes, made

    out: list[dict | None] = [None] * len(questions)
    with ThreadPoolExecutor(max_workers=max(1, min(SET_PARALLEL, len(chunks)))) as pool:
        for indexes, made in pool.map(one, chunks):
            for i, ref in zip(indexes, made):
                out[i] = ref
    return out


def build_paper(user, title: str, raw_questions) -> tuple[object, list[str]]:
    """The paper as a mock test ready to sit, and the labels of the questions
    left out (no answer could be found, or a written one could not be given
    a rubric to mark it by). PracticeUnavailable when none is left."""
    from django.db import transaction
    from quizzes.models import MockTest, MockTestQuestion

    questions = clean(raw_questions)
    if not questions:
        raise PracticeUnavailable(_('No problem could be found in this file.'))
    keys = {i: (q['answer'].upper() if q['kind'] == 'choice' else q['answer'])
            for i, q in enumerate(questions) if q['kind'] in KEYED and fits(q, q['answer'])}
    unsolved = [i for i, q in enumerate(questions) if q['kind'] in KEYED and i not in keys]
    if unsolved:
        try:
            solved = solve_keys([questions[i] for i in unsolved])
        except PracticeUnavailable:
            if len(unsolved) == len(questions):
                raise
            solved = {}
        keys.update({unsolved[j]: key for j, key in solved.items()})
    written = [i for i, q in enumerate(questions) if q['kind'] == 'written']
    rubrics = dict(zip(written, _rubrics([questions[i] for i in written]))) if written else {}

    rows, dropped = [], []
    for i, q in enumerate(questions):
        keep = {'figures': q['figures'], 'paper_question': {**{k: q[k] for k in (
            'label', 'instruction', 'text', 'kind', 'options', 'statements')}, 'answer': keys.get(i)}}
        # The part's instruction ("choose one option") is said by the part's
        # name on the paper; on each question it was the same lines 18 times.
        stem = q['text'] or q['instruction']
        if q['kind'] == 'choice' and i in keys:
            options = [f"{o['label']}. {o['text']}" for o in q['options']]
            correct = next(text for o, text in zip(q['options'], options) if o['label'] == keys[i])
            rows.append({'section': 'choice', 'question_text': stem, 'options': options,
                         'correct_answer': correct, 'reference': keep})
        elif q['kind'] == 'true_false' and i in keys:
            rows.append({'section': 'true_false', 'question_text': stem, 'reference': keep,
                         'statements': [{**s, 'answer': keys[i][s['label']]} for s in q['statements']]})
        elif q['kind'] == 'short' and i in keys:
            rows.append({'section': 'short', 'question_text': stem, 'correct_answer': str(keys[i])[:500],
                         'reference': {**keep, 'answer': keys[i], 'accept': []}})
        elif q['kind'] == 'written' and rubrics.get(i):
            rows.append({'section': 'written', 'question_text': stem,
                         'reference': {**rubrics[i], 'kind': 'written', **keep}})
        else:
            dropped.append(q['label'] or str(i + 1))
    if not rows:
        raise PracticeUnavailable(_('The problems could not be read just now. Try again in a minute.'))
    minutes = weigh(rows)
    with transaction.atomic():
        test = MockTest.objects.create(user=user, notebook=None, template='paper', paper_title=title[:200],
                                       question_count=len(rows), duration_minutes=minutes)
        MockTestQuestion.objects.bulk_create([MockTestQuestion(mock_test=test, order=n, **fields)
                                              for n, fields in enumerate(rows)])
    return test, dropped


def _key_reference(pq: dict) -> dict:
    """A missed keyed question as practice keeps it, before its solution is written."""
    kind, key = pq['kind'], pq['answer']
    ref = {'kind': kind, 'pending': True, 'language': language_of(as_printed(pq))}
    if kind == 'choice':
        ref.update(options=pq['options'], answer=key)
    elif kind == 'true_false':
        ref.update(statements=[{**s, 'answer': key[s['label']]} for s in pq['statements']])
    else:
        ref.update(answer=key, accept=[])
    return ref


def misses_to_practice(test, rows) -> None:
    """The paper's missed questions, as one practice set due today. A written
    one keeps the rubric it was marked by; a keyed one has its solution
    written in the background (fill_pending)."""
    from django.utils import timezone
    from ..models import Exercise
    missed = [r for r in rows if not r.is_correct and (r.reference or {}).get('paper_question')]
    if not missed:
        return
    key, today = uuid.uuid4().hex, timezone.localdate()
    made = []
    for r in missed:
        pq = r.reference['paper_question']
        if pq['kind'] == 'written':
            reference = {k: v for k, v in r.reference.items() if k not in ('figures', 'paper_question')}
        else:
            reference = _key_reference(pq)
        made.append(Exercise(user=test.user, notebook=None, origin='own', set_key=key,
                             set_title=test.paper_title[:200], prompt=as_printed(pq), reference=reference,
                             figures=r.reference.get('figures') or [], status='revisit', revisit_on=today))
    created = Exercise.objects.bulk_create(made)
    pending = [e.id for e in created if e.reference.get('pending')]
    if pending:
        # The first few now, so the set opens ready; the rest when opened
        # (ExerciseDetailView): a paper left half blank would otherwise spend
        # ten requests on solutions nobody may read.
        _in_background(lambda: fill_pending(pending[:BACKGROUND_FILL]))


def _in_background(work) -> None:
    """Run `work` on a thread of its own, after the response has gone."""
    def run():
        from django.db import close_old_connections
        try:
            work()
        except Exception:  # noqa: BLE001 - a later open of the problem tries again
            logger.warning('Writing the solutions of missed questions failed', exc_info=True)
        finally:
            close_old_connections()
    threading.Thread(target=run, daemon=True).start()


def _printed(ref: dict):
    if ref['kind'] == 'true_false':
        return {s['label']: s['answer'] for s in ref.get('statements') or []}
    return ref.get('answer')


def fill_pending(ids) -> None:
    """Write the model solution of missed questions still waiting for one,
    keeping the paper's own answer."""
    from ..models import Exercise
    exercises = [e for e in Exercise.objects.filter(id__in=ids) if (e.reference or {}).get('pending')]
    if not exercises:
        return
    shapes = [{'instruction': '', 'text': e.prompt, 'kind': 'written', 'figures': e.figures} for e in exercises]
    refs = _rubrics(shapes, [_printed(e.reference) for e in exercises])
    for exercise, ref in zip(exercises, refs):
        if ref is None:
            continue
        kept = {k: exercise.reference[k] for k in ('kind', 'options', 'statements', 'answer', 'accept')
                if k in exercise.reference}
        exercise.reference = {**ref, **kept}
        exercise.save(update_fields=['reference'])
