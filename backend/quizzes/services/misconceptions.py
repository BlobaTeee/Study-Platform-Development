"""Chỗ hay nhầm: what a student keeps confusing, read from the wrong options they chose.

A wrong answer records more than a miss: the option picked is what the
student took the right answer to be. The same mix-up in two or more
different questions is a misconception ("usability goals taken for UX
goals"), and it is fixed by setting the two ideas side by side, not by
redoing the questions.

Per notebook, the latest wrong answers go to the model once, which names
the recurring mix-ups and writes two or three contrast cards for each. A
mix-up is kept only when at least `MIN_EVIDENCE` of the listed answers show
it: a single slip is not a misconception. The finding is cached against the
exact set of wrong answers, so it is asked for again only when they change.
"""
import hashlib
import logging
import threading

from django.conf import settings
from django.core.cache import cache

from ml_pipeline.language import detect_language, language_name
from notebooks.services.ai_provider import get_ai_provider
from notebooks.services.writing_style import WRITING_STYLE, tidy_prose, tidy_question

logger = logging.getLogger(__name__)

MIN_WRONG = 3          # fewer, and there is nothing to see a pattern in
MAX_WRONG = 40         # the latest ones; older mistakes may be fixed already
MIN_EVIDENCE = 2
MAX_CARDS = 3
FINDING_TTL = 60 * 60 * 24


def wrong_answers(user) -> dict[int, list[dict]]:
    """notebook id -> the student's wrong answers there, latest first:
    {id, question, right, chose, source_id}. One per question and choice."""
    from quizzes.models import Answer, MockTestQuestion

    rows = []
    for r in (MockTestQuestion.objects
              .filter(mock_test__user=user, mock_test__completed_at__isnull=False, is_correct=False)
              .exclude(user_answer='')
              .values('id', 'question_text', 'correct_answer', 'user_answer', 'source_id',
                      'mock_test__notebook_id', 'answered_at')):
        rows.append({'id': f"m{r['id']}", 'question': r['question_text'], 'right': r['correct_answer'],
                     'chose': r['user_answer'], 'source_id': r['source_id'],
                     'notebook_id': r['mock_test__notebook_id'], 'when': r['answered_at']})
    for r in (Answer.objects.filter(quiz_attempt__user=user, is_correct=False)
              .exclude(user_answer='')
              .values('id', 'question__question_text', 'question__correct_answer', 'user_answer',
                      'question__source_id', 'question__source__notebook_id', 'answered_at')):
        if r['question__source__notebook_id'] is None:
            continue
        rows.append({'id': f"a{r['id']}", 'question': r['question__question_text'],
                     'right': r['question__correct_answer'], 'chose': r['user_answer'],
                     'source_id': r['question__source_id'],
                     'notebook_id': r['question__source__notebook_id'], 'when': r['answered_at']})

    rows.sort(key=lambda r: (r['when'] is not None, r['when']), reverse=True)
    out: dict[int, list[dict]] = {}
    seen = set()
    for r in rows:
        mark = (r['notebook_id'], r['question'].strip().lower(), r['chose'].strip().lower())
        if mark in seen or r['notebook_id'] is None:
            continue
        seen.add(mark)
        bucket = out.setdefault(r['notebook_id'], [])
        if len(bucket) < MAX_WRONG:
            bucket.append(r)
    return out


def misconceptions(user) -> tuple[list[dict], bool]:
    """([{notebook_id, title, items}] for notebooks with a named mix-up,
    pending). Each item: {key, confused, with, difference, evidence,
    examples, cards, source_ids}. `pending` is True while a finding is being
    asked for in the background (see `_finding`)."""
    from notebooks.models import Notebook

    by_notebook = wrong_answers(user)
    titles = dict(Notebook.objects.filter(id__in=list(by_notebook)).values_list('id', 'title'))
    out, pending = [], False
    for nb_id, rows in by_notebook.items():
        if len(rows) < MIN_WRONG:
            continue
        items = _finding(nb_id, rows)
        if items is None:
            pending = True
        elif items:
            out.append({'notebook_id': nb_id, 'title': titles.get(nb_id, ''), 'items': items})
    return sorted(out, key=lambda nb: -sum(i['evidence'] for i in nb['items'])), pending


def find_item(user, notebook_id: int, key: str) -> dict | None:
    for nb in misconceptions(user)[0]:
        if nb['notebook_id'] == notebook_id:
            for item in nb['items']:
                if item['key'] == key:
                    return item
    return None


# Findings being asked for right now, by cache key, so a page polling while
# one runs does not start another.
_running: dict[str, threading.Thread] = {}
_running_lock = threading.Lock()


def wait_for_background(timeout: float = 30) -> None:
    """Let background findings finish (used by tests)."""
    for thread in list(_running.values()):
        thread.join(timeout)


def _finding(notebook_id: int, rows: list[dict]) -> list[dict] | None:
    """The cached finding, or None while it is being asked for.

    With every model busy, a request walks the whole list at 30 seconds a
    model: two minutes before it gives up, and this runs when the progress
    page loads. So the request goes on a thread of its own and the page says
    the finding is on its way; the next look reads it from the cache.
    """
    ids = ','.join(sorted(r['id'] for r in rows))
    cache_key = 'misconceptions:' + hashlib.sha1(f'{notebook_id}:{ids}'.encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    if not getattr(settings, 'MISCONCEPTIONS_IN_BACKGROUND', True):
        found = _ask(rows)
        if found is None:
            return []           # a failure is not remembered: asked again next time
        cache.set(cache_key, found, FINDING_TTL)
        return found
    with _running_lock:
        running = _running.get(cache_key)
        if running is None or not running.is_alive():
            thread = threading.Thread(target=_find_in_background, args=(cache_key, rows), daemon=True)
            _running[cache_key] = thread
            thread.start()
    return None


def _find_in_background(cache_key: str, rows: list[dict]) -> None:
    try:
        found = _ask(rows)
        if found is not None:
            cache.set(cache_key, found, FINDING_TTL)
    finally:
        with _running_lock:
            _running.pop(cache_key, None)


def _ask(rows: list[dict]) -> list[dict] | None:
    listed = '\n'.join(f'{i}. Question: {r["question"]} | Right answer: {r["right"]} | Student chose: {r["chose"]}'
                       for i, r in enumerate(rows, 1))
    lang = language_name(detect_language(' '.join(r['question'] for r in rows)))
    prompt = f"""These are a student's wrong answers. Find what the student keeps confusing: the same
two ideas mixed up in at least {MIN_EVIDENCE} of these answers, judged by what the student chose
instead of the right answer. Do not name a confusion from a single answer, and return an empty
list if nothing recurs.

For each confusion give, in {lang}:
- "confused": the idea the right answers are about, in 1 to 5 words;
- "with": what the student took it for, in 1 to 5 words;
- "difference": one or two sentences saying how the two differ;
- "answers": the numbers of the answers that show it;
- "cards": {MAX_CARDS} or fewer short flashcards that set the two ideas side by side
  ({{"question": "...", "answer": "..."}}, answers of at most 12 words).

{WRITING_STYLE}

Wrong answers:
{listed}

Return ONLY valid JSON: {{"misconceptions": [{{"confused": "...", "with": "...", "difference": "...", "answers": [1, 2], "cards": [{{"question": "...", "answer": "..."}}]}}]}}"""
    try:
        data = get_ai_provider().generate_json(prompt)
    except Exception as exc:  # noqa: BLE001 — no provider, quota, bad JSON: try again later
        logger.info('Finding misconceptions failed: %s', exc)
        return None
    raw = data.get('misconceptions') if isinstance(data, dict) else None
    return [item for m in (raw if isinstance(raw, list) else []) if (item := _checked(m, rows))]


def _checked(m, rows: list[dict]) -> dict | None:
    if not isinstance(m, dict):
        return None
    confused = tidy_prose(str(m.get('confused') or '')).rstrip('.')[:80]
    taken_for = tidy_prose(str(m.get('with') or '')).rstrip('.')[:80]
    picked = m.get('answers') if isinstance(m.get('answers'), list) else []
    evidence = [rows[n - 1] for n in dict.fromkeys(picked)
                if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= len(rows)]
    # Different questions, not one question answered wrong twice.
    questions = {r['question'].strip().lower() for r in evidence}
    if not confused or not taken_for or len(questions) < MIN_EVIDENCE:
        return None
    cards = []
    for c in m.get('cards') if isinstance(m.get('cards'), list) else []:
        if isinstance(c, dict) and str(c.get('question') or '').strip() and str(c.get('answer') or '').strip():
            cards.append({'question': tidy_question(str(c['question'])), 'answer': tidy_prose(str(c['answer']))})
    return {
        'key': hashlib.sha1(f'{confused.lower()}|{taken_for.lower()}'.encode()).hexdigest()[:12],
        'confused': confused,
        'with': taken_for,
        'difference': tidy_prose(str(m.get('difference') or ''))[:400],
        'evidence': len(questions),
        'examples': [r['question'] for r in evidence][:3],
        'cards': cards[:MAX_CARDS],
        'source_ids': sorted({r['source_id'] for r in evidence if r['source_id']}),
    }
