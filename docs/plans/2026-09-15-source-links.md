# Source Links as Relations — Implementation Plan

**Goal:** Replace the `source:1,3` text tag on flashcards and quizzes with a real many-to-many relation to `notebooks.Source`, and remove every parser and builder of that tag.

**Architecture:** Add the M2M and copy the old tags into it first, leaving the old columns in place. Then move readers to the relation one area at a time (analytics → mock-test pool → notebook counts/study sessions/serializers → frontend), then move the writers, and only then drop the old columns. Every commit runs against the database as it stands at that commit.

**Tech Stack:** Django 5.2 + DRF (backend), Next.js 16 / TypeScript (frontend), pytest for pure functions in `tests/`, `manage.py shell` for ORM verification.

**Spec:** `docs/specs/2026-09-15-source-links-design.md`

## Global Constraints

- Backend Python: `backend/venv/bin/python` (3.13). Pure tests: `.venv/bin/pytest -q` from the repo root.
- Tests in `tests/` load modules via `importlib` with no Django — anything tested there must stay Django-free.
- Every `manage.py shell` verification that writes must run inside `transaction.atomic()` and raise to roll back, unless it is the migration itself.
- Between Task 1 and Task 6 do **not** generate content on the dev database: new items would carry a tag but no through rows. If it happens, re-run `copy_tags_to_sources` from the shell.
- Dev database facts measured 2026-09-15: sources `[9, 11, 18]` exist; 40 flashcards → 20 live links; 15 quizzes → 5 live links.

---

### Task 1: Add the relation and copy the old tags into it

**Files:**
- Modify: `backend/flashcards/models.py:15-24` (add `sources` after `notebook`)
- Modify: `backend/quizzes/models.py:5-14` (add `sources` after `description`)
- Create: `backend/flashcards/migrations/0006_flashcard_sources.py`
- Create: `backend/quizzes/migrations/0005_quiz_sources.py`

**Interfaces:**
- Produces: `Flashcard.sources` (M2M → `notebooks.Source`, `related_name='flashcards'`), `Quiz.sources` (M2M, `related_name='quizzes'`). Through models reachable as `Flashcard.sources.through` (fields `flashcard_id`, `source_id`) and `Quiz.sources.through` (`quiz_id`, `source_id`).

- [ ] **Step 1: Add the fields**

In `backend/flashcards/models.py`, directly after the `notebook` field:

```python
    # The documents this card was generated from. Empty for a card written by
    # hand through the API. Deleting a source unlinks it here; the card stays.
    sources = models.ManyToManyField(
        'notebooks.Source', related_name='flashcards', blank=True,
        help_text='The documents this card was generated from.',
    )
```

In `backend/quizzes/models.py`, directly after `description`:

```python
    # The documents this quiz was generated from; `description` used to carry
    # this as a "[source:1,3]" suffix. Empty for a quiz authored directly.
    sources = models.ManyToManyField(
        'notebooks.Source', related_name='quizzes', blank=True,
        help_text='The documents this quiz was generated from.',
    )
```

- [ ] **Step 2: Write the flashcards migration**

`backend/flashcards/migrations/0006_flashcard_sources.py`:

```python
"""Copy the `source:1,3` tag into a real relation. `tags` itself is removed
in 0007, once nothing reads it any more."""
import re

from django.db import migrations, models

_TAG = re.compile(r'source:([\d,]+)')


def _ids(text):
    match = _TAG.search(text or '')
    return [int(p) for p in match.group(1).split(',') if p] if match else []


def copy_tags_to_sources(apps, schema_editor):
    Flashcard = apps.get_model('flashcards', 'Flashcard')
    Source = apps.get_model('notebooks', 'Source')
    Through = Flashcard.sources.through
    # Ids of sources that no longer exist are dropped: carrying them was the
    # orphan problem this relation replaces.
    existing = set(Source.objects.values_list('id', flat=True))
    rows = [
        Through(flashcard_id=card_id, source_id=sid)
        for card_id, tags in Flashcard.objects.values_list('id', 'tags')
        for sid in _ids(tags) if sid in existing
    ]
    Through.objects.bulk_create(rows, ignore_conflicts=True)


def rebuild_tags_from_sources(apps, schema_editor):
    Flashcard = apps.get_model('flashcards', 'Flashcard')
    for card in Flashcard.objects.prefetch_related('sources'):
        ids = sorted(s.id for s in card.sources.all())
        card.tags = f"source:{','.join(map(str, ids))}" if ids else None
        card.save(update_fields=['tags'])


class Migration(migrations.Migration):
    dependencies = [
        ('flashcards', '0005_link_flashcards_to_notebooks'),
        ('notebooks', '0002_source_file_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='flashcard',
            name='sources',
            field=models.ManyToManyField(
                blank=True, help_text='The documents this card was generated from.',
                related_name='flashcards', to='notebooks.source'),
        ),
        migrations.RunPython(copy_tags_to_sources, rebuild_tags_from_sources),
    ]
```

- [ ] **Step 3: Write the quizzes migration**

`backend/quizzes/migrations/0005_quiz_sources.py`:

```python
"""Copy the "[source:1,3]" suffix quizzes carried in `description` into a real
relation. The suffix itself is stripped in 0006, once nothing reads it."""
import re

from django.db import migrations, models

_TAG = re.compile(r'source:([\d,]+)')


def _ids(text):
    match = _TAG.search(text or '')
    return [int(p) for p in match.group(1).split(',') if p] if match else []


def copy_description_tags_to_sources(apps, schema_editor):
    Quiz = apps.get_model('quizzes', 'Quiz')
    Source = apps.get_model('notebooks', 'Source')
    Through = Quiz.sources.through
    existing = set(Source.objects.values_list('id', flat=True))
    rows = [
        Through(quiz_id=quiz_id, source_id=sid)
        for quiz_id, description in Quiz.objects.values_list('id', 'description')
        for sid in _ids(description) if sid in existing
    ]
    Through.objects.bulk_create(rows, ignore_conflicts=True)


def restore_description_tags(apps, schema_editor):
    Quiz = apps.get_model('quizzes', 'Quiz')
    for quiz in Quiz.objects.prefetch_related('sources'):
        ids = sorted(s.id for s in quiz.sources.all())
        if not ids:
            continue
        tag = f"[source:{','.join(map(str, ids))}]"
        if tag not in (quiz.description or ''):
            quiz.description = f"{quiz.description or ''} {tag}".strip()
            quiz.save(update_fields=['description'])


class Migration(migrations.Migration):
    dependencies = [
        ('quizzes', '0004_mock_test_review_freeze_and_reminder_skip'),
        ('notebooks', '0002_source_file_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='quiz',
            name='sources',
            field=models.ManyToManyField(
                blank=True, help_text='The documents this quiz was generated from.',
                related_name='quizzes', to='notebooks.source'),
        ),
        migrations.RunPython(copy_description_tags_to_sources, restore_description_tags),
    ]
```

- [ ] **Step 4: Confirm Django agrees the migrations match the models**

Run: `cd backend && ./venv/bin/python manage.py makemigrations --check --dry-run`
Expected: `No changes detected` (if it proposes a migration, the field definition and the migration disagree — fix the migration, not the model).

- [ ] **Step 5: Migrate and verify the copy**

Run: `cd backend && ./venv/bin/python manage.py migrate`
Then:

```bash
cd backend && ./venv/bin/python manage.py shell -c "
from flashcards.models import Flashcard
from quizzes.models import Quiz
print('flashcard links:', Flashcard.sources.through.objects.count())
print('quiz links     :', Quiz.sources.through.objects.count())
"
```
Expected: `flashcard links: 20`, `quiz links     : 5`.

- [ ] **Step 6: Verify the round trip**

```bash
cd backend && ./venv/bin/python manage.py shell -c "
from flashcards.models import Flashcard
from quizzes.models import Quiz
before = dict(Flashcard.objects.values_list('id', 'tags'))
before_q = dict(Quiz.objects.values_list('id', 'description'))
import pickle; pickle.dump((before, before_q), open('/tmp/tags_snapshot.pkl', 'wb'))
"
./venv/bin/python manage.py migrate flashcards 0005 && ./venv/bin/python manage.py migrate quizzes 0004
./venv/bin/python manage.py shell -c "
import pickle, re
from flashcards.models import Flashcard
from quizzes.models import Quiz
from notebooks.models import Source
before, before_q = pickle.load(open('/tmp/tags_snapshot.pkl', 'rb'))
live = set(Source.objects.values_list('id', flat=True))
def ids(t):
    m = re.search(r'source:([\d,]+)', t or ''); return [int(p) for p in m.group(1).split(',') if p] if m else []
changed = [(i, before[i], t) for i, t in Flashcard.objects.values_list('id', 'tags') if t != before[i]]
# Only cards whose old tag named a source that no longer exists may differ.
assert all(not any(s in live for s in ids(old)) for _, old, _ in changed), changed
changed_q = [(i, before_q[i], d) for i, d in Quiz.objects.values_list('id', 'description') if d != before_q[i]]
assert all(not any(s in live for s in ids(old)) for _, old, _ in changed_q), changed_q
print('round trip OK; orphan-only rows lost their tag:', len(changed), 'cards,', len(changed_q), 'quizzes')
"
./venv/bin/python manage.py migrate
```
Expected: the assertion passes and the final `migrate` re-applies both migrations. Re-run Step 5's count check afterwards: still 20 and 5.

- [ ] **Step 7: Run the suite (nothing in `tests/` touches models, so this is a smoke check) and commit**

Run: `.venv/bin/pytest -q` — Expected: `311 passed`.

```bash
git add backend/flashcards/models.py backend/quizzes/models.py backend/flashcards/migrations/0006_flashcard_sources.py backend/quizzes/migrations/0005_quiz_sources.py
git commit -m "feat(sources): link flashcards and quizzes to their sources by relation

Adds Flashcard.sources and Quiz.sources (M2M to notebooks.Source) and
copies the existing source:1,3 tags into them. The tag columns stay for
now: readers are moved over one area at a time in the commits that
follow, and the columns go once nothing reads them.

Ids that named a deleted source are dropped in the copy — 20 of 40
flashcard links and 11 of 16 quiz links on the dev database were exactly
that kind of orphan."
```

---

### Task 2: Analytics reads sources from the relation

**Files:**
- Modify: `backend/analytics/insights.py:11-121` (delete `re` import, `SOURCE_TAG_PREFIX`, `_SOURCE_TAG_RE`, `parse_source_ids`; adapters read `source_ids`)
- Modify: `backend/analytics/views.py:1-12,64-115`
- Test: `tests/test_analytics_insights.py:27-83`

**Interfaces:**
- Consumes: `Flashcard.sources.through` (Task 1).
- Produces: `insights.flashcard_events(cards)` where each card dict carries `source_ids: list[int]`; `insights.quiz_events(questions, answers)` where each question dict carries `source_ids: list[int]`. `analytics.views._sources_by_flashcard(user) -> dict[int, list[int]]`.

- [ ] **Step 1: Rewrite the adapter tests to hand over `source_ids`, and delete the parser tests**

In `tests/test_analytics_insights.py`, delete the whole `# ---- parse_source_ids` section (the three `test_parses_*` / `test_parse_handles_*` functions). Replace the three study-event tests with:

```python
# ---- study events ----------------------------------------------------------
# "How well do I know this document?" must not depend on which study mode
# produced the evidence, so each mode is adapted to a common event shape and a
# new mode later only needs its own adapter. Source ids arrive already
# resolved from the relation; the adapters do no parsing.

def test_flashcard_events_carry_the_cards_review_tally():
    events = ins.flashcard_events([
        {"id": 1, "source_ids": [3], "correct_count": 2, "incorrect_count": 1}
    ])
    assert events == [
        {"kind": ins.KIND_FLASHCARD, "source_ids": [3], "correct": 2, "incorrect": 1}
    ]


def test_quiz_events_count_each_questions_answers():
    questions = [{"id": 9, "source_ids": [3]}]
    answers = [{"question_id": 9, "is_correct": True},
               {"question_id": 9, "is_correct": False}]
    assert ins.quiz_events(questions, answers) == [
        {"kind": ins.KIND_QUIZ, "source_ids": [3], "correct": 1, "incorrect": 1}
    ]


def test_unanswered_quiz_question_is_still_an_item():
    # Mirrors an unreviewed flashcard: something left to study, no evidence yet.
    events = ins.quiz_events([{"id": 9, "source_ids": [3]}], [])
    assert events[0]["correct"] == 0
    assert events[0]["incorrect"] == 0


def test_an_item_with_no_sources_is_still_an_event():
    # A hand-written card, or one whose only source was deleted: it is studied
    # like any other, it just counts toward no document.
    events = ins.flashcard_events([{"id": 1, "correct_count": 1, "incorrect_count": 0}])
    assert events == [
        {"kind": ins.KIND_FLASHCARD, "source_ids": [], "correct": 1, "incorrect": 0}
    ]
```

- [ ] **Step 2: Run the file, expect the four to fail**

Run: `.venv/bin/pytest tests/test_analytics_insights.py -q`
Expected: 4 failed (`source_ids` still parsed from `tags`, so `[]` comes back; the last test fails on the missing key path), rest pass.

- [ ] **Step 3: Rewrite the adapters**

In `backend/analytics/insights.py`: delete `import re`, the `SOURCE_TAG_PREFIX = "source:"` line, the `_SOURCE_TAG_RE` block with its comment, and `parse_source_ids`. Replace the two adapters with:

```python
def flashcard_events(cards: list[dict]) -> list[dict]:
    """Adapt flashcards (with review counts attached) to study events.

    `source_ids` is the card's resolved relation; a card with none — written
    by hand, or whose documents were deleted — is still an event, it just
    counts toward no document.
    """
    return [
        {
            "kind": KIND_FLASHCARD,
            "source_ids": list(card.get("source_ids", [])),
            "correct": card.get("correct_count", 0),
            "incorrect": card.get("incorrect_count", 0),
        }
        for card in cards
    ]


def quiz_events(questions: list[dict], answers: list[dict]) -> list[dict]:
    """Adapt quiz questions and the user's answers to study events.

    Quiz answers are graded by the app rather than self-reported, so they are
    the firmer of the two kinds of evidence. Every question is an event, even
    an unanswered one — like an unreviewed card, it is still something to study.
    """
    tallies: dict[int, dict[str, int]] = {}
    for answer in answers:
        bucket = tallies.setdefault(answer["question_id"], {"correct": 0, "incorrect": 0})
        bucket["correct" if answer.get("is_correct") else "incorrect"] += 1

    return [
        {
            "kind": KIND_QUIZ,
            "source_ids": list(question.get("source_ids", [])),
            "correct": tallies.get(question["id"], {}).get("correct", 0),
            "incorrect": tallies.get(question["id"], {}).get("incorrect", 0),
        }
        for question in questions
    ]
```

- [ ] **Step 4: Run the file, expect green**

Run: `.venv/bin/pytest tests/test_analytics_insights.py -q`
Expected: all pass (29).

- [ ] **Step 5: Supply `source_ids` from the view**

In `backend/analytics/views.py`, change the first import line to `from django.db.models import Avg` (drop `F`), and add after `_review_tallies`:

```python
def _sources_by_flashcard(user):
    """Flashcard id -> ids of the sources it was generated from.

    One query over the through table for the whole collection, instead of a
    prefetch per card; the analytics page reads every card the user has.
    """
    by_card: dict[int, list[int]] = {}
    for card_id, source_id in (Flashcard.sources.through.objects
                               .filter(flashcard__user=user)
                               .values_list('flashcard_id', 'source_id')):
        by_card.setdefault(card_id, []).append(source_id)
    return by_card


def _questions_with_sources(user):
    """Every question the user owns as {'id', 'source_ids'}, one query.

    `values('id', 'quiz__sources')` yields one row per (question, source) and
    a row with `None` for a quiz with no sources, so rows are folded here.
    """
    by_question: dict[int, list[int]] = {}
    for row in Question.objects.filter(quiz__user=user).values('id', 'quiz__sources'):
        ids = by_question.setdefault(row['id'], [])
        if row['quiz__sources'] is not None:
            ids.append(row['quiz__sources'])
    return [{'id': qid, 'source_ids': ids} for qid, ids in by_question.items()]
```

In `recommendations`, replace the `cards = insights.attach_review_counts(...)` block with:

```python
        by_card = _sources_by_flashcard(user)
        cards = insights.attach_review_counts(
            # Archived originals keep their old next_review_date forever, so an
            # unfiltered count here would drift from due_today's own filtered
            # queryset and never come back into agreement.
            [{'id': c['id'], 'source_ids': by_card.get(c['id'], [])}
             for c in Flashcard.objects.filter(user=user, archived=False).values('id')],
            _review_tallies(user),
        )
```

and the `events = ...` block with:

```python
        events = insights.flashcard_events(cards) + insights.quiz_events(
            _questions_with_sources(user),
            list(Answer.objects.filter(quiz_attempt__user=user)
                 .values('question_id', 'is_correct')),
        )
```

- [ ] **Step 6: Verify against the dev database**

```bash
cd backend && ./venv/bin/python manage.py shell -c "
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
c = APIClient(HTTP_HOST='localhost'); c.force_authenticate(get_user_model().objects.get(id=2))
r = c.get('/api/analytics/sessions/recommendations/')
print(r.status_code, r.json()['weak_notebooks'])
"
```
Expected: `200` and a non-empty `weak_notebooks` list — the same notebooks as before Task 1 (the relation was copied from the tags, so mastery must not change).

- [ ] **Step 7: Suite and commit**

Run: `.venv/bin/pytest -q` — Expected: `309 passed` (311 before, minus the 3 parser tests, plus the no-sources test).

```bash
git add backend/analytics/insights.py backend/analytics/views.py tests/test_analytics_insights.py
git commit -m "refactor(analytics): read an item's sources from the relation

The adapters take source_ids that the view resolved from
Flashcard.sources / Quiz.sources; parse_source_ids and its regex are gone."
```

---

### Task 3: Mock-test pool and accuracy read the relation

**Files:**
- Modify: `backend/quizzes/views.py:1,102-228` (delete `_source_filter`; rewrite `_question_pool` and `_source_accuracy`; drop `Q` import)

**Interfaces:**
- Consumes: `Quiz.sources` (Task 1).
- Produces: `_question_pool(user, source_ids) -> list[{'id', 'source_ids'}]` (unchanged shape), `_source_accuracy(user, source_ids) -> dict[int, float]` (unchanged).

- [ ] **Step 1: Replace the three functions**

Delete `_source_filter` entirely (lines 102–122) and the `from django.db.models import Q` import. Replace `_question_pool` and `_source_accuracy` with:

```python
def _question_pool(user, source_ids):
    """Every question generated from this notebook's documents, each with the
    subset of those documents it came from.

    Filtering and reading `quiz__sources` in the same query reuses one join,
    so the ids that come back are only the selected ones.
    """
    if not source_ids:
        return []
    pool: dict[int, list[int]] = {}
    for row in (Question.objects
                .filter(quiz__user=user, quiz__sources__in=source_ids)
                .values('id', 'quiz__sources')):
        pool.setdefault(row['id'], []).append(row['quiz__sources'])
    return [{'id': qid, 'source_ids': ids} for qid, ids in pool.items()]


def _source_accuracy(user, source_ids):
    """How well the user has answered questions from this notebook's own
    documents so far — the weighting has no use for accuracy on unrelated
    material, so this is scoped rather than pulling the user's whole history.

    One row per (answer, source): an answer to a question drawn from two of
    the selected documents counts for each, which is what `source_accuracy`
    expects.
    """
    if not source_ids:
        return {}
    rows = [
        {'source_ids': [row['question__quiz__sources']], 'is_correct': row['is_correct']}
        for row in Answer.objects
        .filter(quiz_attempt__user=user, question__quiz__sources__in=source_ids)
        .values('question__quiz__sources', 'is_correct')
    ]
    return source_accuracy(rows)
```

- [ ] **Step 2: Check nothing else imported what was removed**

Run: `grep -n "_source_filter\|insights\.\|Q(" backend/quizzes/views.py`
Expected: no output (if `insights.` still appears, that use must be replaced or the import kept; if `Q(` appears, keep the import).

- [ ] **Step 3: Verify by starting a test, rolled back**

```bash
cd backend && ./venv/bin/python manage.py shell -c "
from django.db import transaction
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from notebooks.models import Notebook
from quizzes.views import _question_pool, _source_accuracy
u = get_user_model().objects.get(id=2)
nb = Notebook.objects.filter(user=u).first()
from quizzes.models import Question
ids = list(nb.sources.values_list('id', flat=True))
pool = _question_pool(u, ids)
expected = Question.objects.filter(quiz__user=u, quiz__sources__in=ids).distinct().count()
assert len(pool) == expected, (len(pool), expected)          # no cross-join inflation
assert all(set(q['source_ids']) <= set(ids) for q in pool)  # only the selected sources
print('pool size:', len(pool), '(matches distinct count) | accuracy:', _source_accuracy(u, ids))
c = APIClient(HTTP_HOST='localhost'); c.force_authenticate(u)
class Rollback(Exception): pass
try:
    with transaction.atomic():
        r = c.post('/api/quizzes/mock-tests/', {'notebook': nb.id, 'question_count': 5, 'duration_minutes': 10}, format='json')
        print('start:', r.status_code, r.json().get('detail') or f\"{len(r.json().get('questions', []))} questions\")
        raise Rollback
except Rollback: pass
"
```
Expected: both assertions hold and the pool size prints; `start: 201` with questions (or `429` if the generation throttle from earlier today is still counting — clear it with `from django.core.cache import cache; cache.clear()` and retry).

- [ ] **Step 4: Suite and commit**

Run: `.venv/bin/pytest -q` — Expected: all pass.

```bash
git add backend/quizzes/views.py
git commit -m "refactor(mock-tests): draw the question pool from Quiz.sources

The substring prefilter and the parse-then-check it guarded are replaced
by one join; the ids that come back are exact by construction."
```

---

### Task 4: Deck lookup, study sessions, and serializers read the relation

**Files:**
- Create: `backend/notebooks/services/decks.py`
- Test: `tests/test_decks.py`
- Modify: `backend/notebooks/views.py:17-22,125-163`
- Modify: `backend/study_sessions/views.py:85-125,290-296`
- Modify: `backend/flashcards/serializers.py`, `backend/quizzes/serializers.py:14-24`

**Interfaces:**
- Produces: `decks.items_with_exact_sources(pairs: Iterable[tuple[int, int]], source_ids: Iterable[int]) -> list[int]` — used again by Task 6's `_replace_deck`. API fields `source_ids: list[int]` on `FlashcardSerializer` and `QuizSerializer`; `source_ids` on each entry of `/api/study/sessions/due_today/`'s response (and on `_swap_in_variants` replacements).

- [ ] **Step 1: Write the failing test for the deck helper**

`tests/test_decks.py`:

```python
"""Which items make up "the deck" for a selection of sources."""
import importlib.util
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "notebooks" / "services" / "decks.py")


def _load():
    spec = importlib.util.spec_from_file_location("decks_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


decks = _load()

# (item_id, source_id) pairs, as the through table would hand them over.
PAIRS = [
    (1, 9),            # card 1: [9]
    (2, 9), (2, 11),   # card 2: [9, 11]
    (3, 11),           # card 3: [11]
    (4, 9),            # card 4: [9]
]


def test_exact_set_matches_only_items_with_those_sources_and_no_others():
    assert sorted(decks.items_with_exact_sources(PAIRS, [9])) == [1, 4]


def test_a_superset_is_not_the_same_deck():
    # Card 2 has 9 as well, but it was generated from 9 and 11 together.
    assert 2 not in decks.items_with_exact_sources(PAIRS, [9])


def test_selection_order_does_not_matter():
    assert decks.items_with_exact_sources(PAIRS, [11, 9]) == [2]


def test_empty_selection_matches_nothing():
    assert decks.items_with_exact_sources(PAIRS, []) == []
```

- [ ] **Step 2: Run it, expect failure**

Run: `.venv/bin/pytest tests/test_decks.py -q`
Expected: 4 failed with `FileNotFoundError` / module not found for `decks.py`.

- [ ] **Step 3: Implement the helper**

`backend/notebooks/services/decks.py`:

```python
"""Which items make up "the deck" for a selection of sources.

A deck is everything generated from exactly one selection — the same
documents, no more, no fewer. Regeneration retires the previous deck and the
notebook workspace counts it, so both must agree on what it is.

Computed in Python over (item, source) pairs rather than with chained
many-to-many filters plus an annotate: the ORM's join reuse on multi-valued
relations is exactly the kind of thing that returns a superset without
complaint, and a user's through rows number a few hundred at most.
"""
from __future__ import annotations

from typing import Iterable


def items_with_exact_sources(pairs: Iterable[tuple[int, int]],
                             source_ids: Iterable[int]) -> list[int]:
    """Ids of the items whose linked sources are exactly `source_ids`.

    `pairs` are (item_id, source_id) rows. An item that appears in no pair
    has no sources and can never match; an empty selection matches nothing.
    """
    wanted = set(source_ids)
    if not wanted:
        return []
    by_item: dict[int, set[int]] = {}
    for item_id, source_id in pairs:
        by_item.setdefault(item_id, set()).add(source_id)
    return [item_id for item_id, linked in by_item.items() if linked == wanted]
```

- [ ] **Step 4: Run it, expect green**

Run: `.venv/bin/pytest tests/test_decks.py -q` — Expected: 4 passed.

- [ ] **Step 5: Use it for the existing-material count**

In `backend/notebooks/views.py`, remove `combined_source_tag` from the `from .services.generate import (...)` list and add `from .services.decks import items_with_exact_sources`. Replace the body of the counts action after the `if not source_ids:` early return with:

```python
        # The deck for this exact selection — every selected source and no
        # other — because that is the set a generate press retires, and the
        # number shown must be the number that press costs.
        deck = items_with_exact_sources(
            Flashcard.sources.through.objects
            .filter(flashcard__user=request.user, flashcard__archived=False)
            .values_list('flashcard_id', 'source_id'),
            source_ids)
        quizzes = items_with_exact_sources(
            Quiz.sources.through.objects
            .filter(quiz__user=request.user)
            .values_list('quiz_id', 'source_id'),
            source_ids)
        quiz_id = (Quiz.objects.filter(id__in=quizzes).order_by('-created_at')
                   .values_list('id', flat=True).first())
        return Response({'flashcards': len(deck), 'quiz_id': quiz_id})
```

Delete the `tag = combined_source_tag(source_ids)` line and the two comments about brackets and substrings that preceded the old queries.

- [ ] **Step 6: Study sessions — excerpt and due cards**

In `backend/study_sessions/views.py`:

Replace `_source_excerpt` with:

```python
def _source_excerpt(user, source_ids, limit=4000):
    """The text the card was generated from, so a variant stays on topic."""
    from notebooks.models import Source

    if not source_ids:
        return ""
    texts = Source.objects.filter(
        id__in=source_ids, notebook__user=user
    ).values_list('extracted_text', flat=True)
    return "\n\n".join(t for t in texts if t)[:limit]
```

In `_swap_in_variants`, change the call to `excerpt = _source_excerpt(user, entry.get('source_ids', []))` and the replacement dict's `'tags': new_card.tags,` to `'source_ids': list(new_card.sources.values_list('id', flat=True)),`.

In the due-cards action, replace the `cards = list(Flashcard.objects...values(...))` statement with:

```python
        cards = list(Flashcard.objects.filter(user=user, archived=False)
                     .values('id', 'question', 'answer', 'difficulty',
                             'needs_regeneration', 'regeneration_attempts'))
        # Sources ride along so the study page can scope the due queue to a
        # document (`?due=1&source=…`). One query for the collection.
        by_card: dict[int, list[int]] = {}
        for card_id, source_id in (Flashcard.sources.through.objects
                                   .filter(flashcard__user=user)
                                   .values_list('flashcard_id', 'source_id')):
            by_card.setdefault(card_id, []).append(source_id)
        for card in cards:
            card['source_ids'] = by_card.get(card['id'], [])
```

`rank_due_cards` copies each card dict with `{**card, ...}`, so `source_ids` reaches the response unchanged.

- [ ] **Step 7: Serializers expose `source_ids`, read-only**

`backend/flashcards/serializers.py` — add a field and list it (keep `'tags'` in `fields` for now; Task 7 removes it):

```python
class FlashcardSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source='topic.name', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    # Read-only: provenance is set by generation. A writable list would let a
    # client claim a card belongs to a document it never saw.
    source_ids = serializers.PrimaryKeyRelatedField(
        source='sources', many=True, read_only=True)

    class Meta:
        model = Flashcard
        fields = ['id', 'user', 'username', 'topic', 'topic_name', 'question', 'answer',
                  'difficulty', 'is_public', 'tags', 'source_ids', 'views_count',
                  'correct_count', 'incorrect_count', 'created_at', 'updated_at']
        read_only_fields = ['user', 'views_count', 'correct_count', 'incorrect_count', 'created_at', 'updated_at']
```

`backend/quizzes/serializers.py` — in `QuizSerializer` add the same `source_ids` field declaration and add `'source_ids'` to `fields` after `'description'`.

- [ ] **Step 8: Verify the three surfaces**

```bash
cd backend && ./venv/bin/python manage.py shell -c "
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from notebooks.models import Notebook
u = get_user_model().objects.get(id=2); nb = Notebook.objects.filter(user=u).first()
ids = list(nb.sources.values_list('id', flat=True))
c = APIClient(HTTP_HOST='localhost'); c.force_authenticate(u)
print('counts  :', c.get(f'/api/notebooks/notebooks/{nb.id}/material_counts/?source_ids=' + ','.join(map(str, ids))).json())
f = c.get('/api/flashcards/flashcards/').json(); f = f.get('results', f)
print('flashcard:', {k: f[0][k] for k in ('id', 'tags', 'source_ids')})
d = c.get('/api/study/sessions/due_today/').json()
print('due      :', [(e['id'], e['source_ids']) for e in d[:3]])
"
```
Expected: `counts` shows a non-zero `flashcards` for the notebook's selection (it was non-zero before this task — compare with the old tag-based number if in doubt); the flashcard row shows `source_ids` matching the ids in its `tags`; due entries carry `source_ids`.

- [ ] **Step 9: Suite and commit**

Run: `.venv/bin/pytest -q` — Expected: `313 passed`.

```bash
git add backend/notebooks/services/decks.py tests/test_decks.py backend/notebooks/views.py backend/study_sessions/views.py backend/flashcards/serializers.py backend/quizzes/serializers.py
git commit -m "refactor(sources): deck lookup, study sessions and API read the relation

A deck is the items whose sources are exactly the selection —
items_with_exact_sources says so once, for the workspace count now and
for deck retirement next. The API exposes source_ids (read-only) beside
the old tag so the frontend can switch over."
```

---

### Task 5: Frontend filters by `source_ids`

**Files:**
- Modify: `lib/source-utils.ts:30-58`
- Modify: `app/dashboard/flashcards/page.tsx:12-14,24-30,62-74`
- Modify: `app/dashboard/quizzes/page.tsx:10,25-30,44-47`
- Modify: `components/notebook-workspace.tsx:100-103` (comment only)

**Interfaces:**
- Consumes: `source_ids: number[]` on flashcards, quizzes, and due-card entries (Task 4).
- Produces: `hasAllSources(itemSourceIds: number[] | undefined, selected: number[]): boolean`.

- [ ] **Step 1: Replace the matchers in `lib/source-utils.ts`**

Delete `buildSourceTag`, `flashcardMatchesSourceTag`, and `quizMatchesSourceTag`. Add in their place:

```ts
/** Whether an item generated from `itemSourceIds` belongs in a view of
 *  `selected` sources: it must have every one of them. An item from [1, 3]
 *  shows under ?source=1 and under ?source=1,3; an item from [1] does not
 *  show under ?source=1,3. An empty selection matches nothing, which is what
 *  the pages' "pick a document first" guards rely on. */
export function hasAllSources(itemSourceIds: number[] | undefined, selected: number[]): boolean {
  if (!itemSourceIds || selected.length === 0) return false
  return selected.every((id) => itemSourceIds.includes(id))
}
```

- [ ] **Step 2: Flashcards page**

In `app/dashboard/flashcards/page.tsx`: change the import `flashcardMatchesSourceTag,` to `hasAllSources,`; change the type field `tags?: string | null` to `source_ids?: number[]`; change both `allCards.filter((f) => flashcardMatchesSourceTag(f.tags, sourceIds))` to `allCards.filter((f) => hasAllSources(f.source_ids, sourceIds))`.

- [ ] **Step 3: Quizzes page**

In `app/dashboard/quizzes/page.tsx`: import `hasAllSources` instead of `quizMatchesSourceTag`; add `source_ids?: number[]` to the `Quiz` type; change the filter to `allQuizzes.filter((q) => hasAllSources(q.source_ids, sourceIds))`.

- [ ] **Step 4: Workspace comment**

In `components/notebook-workspace.tsx`, replace the four-line comment above the counts `useSWR` with:

```ts
  // Counted server-side as the exact source set, which is the same set
  // generating replaces — so the number shown is always the number a press
  // retires. The page has no card list to count from anyway.
```

- [ ] **Step 5: Typecheck and grep**

Run: `./node_modules/.bin/tsc --noEmit -p tsconfig.json && grep -rn "MatchesSourceTag\|buildSourceTag\|\.tags\b" app components lib`
Expected: `tsc` silent; grep prints nothing.

- [ ] **Step 6: Manual check, then commit**

With `pnpm dev:all` running: open a notebook, tick a source, follow its "Study" link — the flashcards page lists that source's cards as before; Analytics → still renders. Then:

```bash
git add lib/source-utils.ts app/dashboard/flashcards/page.tsx app/dashboard/quizzes/page.tsx components/notebook-workspace.tsx
git commit -m "refactor(web): scope study views by source_ids, not the tag string

hasAllSources replaces the two substring matchers — same intent (show
what touches these documents), without source:1 matching source:13."
```

---

### Task 6: Generation writes the relation

**Files:**
- Modify: `backend/notebooks/services/generate.py:19,88-90,125-219,222-240,282-303,351-363`
- Modify: `backend/notebooks/services/fallback.py` (all four generators)
- Modify: `backend/ml/adapter.py:23-75`
- Modify: `backend/flashcards/services/regeneration.py:77-91`

**Interfaces:**
- Consumes: `items_with_exact_sources` (Task 4).
- Produces: `_replace_deck(cards, user, source_ids, notebook)`; `fallback.generate_flashcards_fallback_multi(sources, user, count)`, `fallback.generate_quiz_fallback_multi(sources, user, question_count)`; `ml.adapter.generate_flashcards_ml(sources, user, count)`, `ml.adapter.generate_quiz_ml(sources, user, question_count)` — the `tag` parameter is gone from all of them.

- [ ] **Step 1: `generate.py` — remove the tag, assign sources in `_replace_deck`**

Delete `SOURCE_TAG_PREFIX = 'source:'` and the `combined_source_tag` function. Add `from .decks import items_with_exact_sources` to the imports.

`_generate_flashcards_ml` / `_generate_quiz_ml` lose their `tag` parameter and pass-through:

```python
def _generate_flashcards_ml(sources, user, count: int) -> list[Flashcard]:
    from ml.adapter import generate_flashcards_ml
    return generate_flashcards_ml(sources, user, count)


def _generate_quiz_ml(sources, user, question_count: int) -> Quiz:
    from ml.adapter import generate_quiz_ml
    return generate_quiz_ml(sources, user, question_count)
```

In `_save_flashcards_from_json`, delete `tag = combined_source_tag(source_ids)` and the `tags=tag,` kwarg.

Replace `_replace_deck` with:

```python
def _replace_deck(cards: list[Flashcard], user, source_ids: list[int], notebook) -> None:
    """Hand the new deck its sources and notebook, and retire the deck it replaces.

    All three writes live here rather than at each creation site because
    there are four of them (LLM, ML-primary, local fallback, regeneration) and
    only this one runs for every provider — the local fallback in particular
    generates from a stand-in object that has no notebook or sources to read.

    Retirement is "every other active card of exactly this selection" rather
    than a list captured before generating, so two generations racing each
    other still leave one deck rather than two. Archiving rather than deleting
    keeps the reviews already recorded against those cards, which analytics
    counts.

    Atomic: a crash between the writes would leave the old deck and the new
    one both live, or a new deck with no sources, which is the stacking and
    the orphaning this exists to prevent.
    """
    fresh_ids = [c.id for c in cards]
    Through = Flashcard.sources.through
    with transaction.atomic():
        Through.objects.bulk_create(
            [Through(flashcard_id=cid, source_id=sid)
             for cid in fresh_ids for sid in source_ids],
            ignore_conflicts=True)
        if notebook is not None:
            Flashcard.objects.filter(id__in=fresh_ids).update(notebook=notebook)
            for card in cards:
                card.notebook = notebook
        previous = items_with_exact_sources(
            Through.objects
            .filter(flashcard__user=user, flashcard__archived=False)
            .exclude(flashcard_id__in=fresh_ids)
            .values_list('flashcard_id', 'source_id'),
            source_ids)
        Flashcard.objects.filter(id__in=previous).update(
            archived=True, needs_regeneration=False)
```

In `generate_flashcards_for_sources`: delete `tag = combined_source_tag(source_ids)`; call `_generate_flashcards(sources, user, count, source_ids, meta)` and `_replace_deck(cards, user, source_ids, notebook)`.

`_generate_flashcards` signature becomes `(sources, user, count, source_ids, meta)`; inside, the ML-primary call is `_generate_flashcards_ml(sources, user, count)` and each `fallback.generate_flashcards_fallback_multi(sources, user, count, tag)` becomes `fallback.generate_flashcards_fallback_multi(sources, user, count)`.

In `generate_quiz_for_sources`: delete `tag = combined_source_tag(source_ids)`; ML-primary call is `_generate_quiz_ml(sources, user, question_count)`; each `fallback.generate_quiz_fallback_multi(sources, user, question_count, tag)` drops `tag`. Replace the block from `tag_note = f' [{tag}]'` through `quiz.save(update_fields=['description'])` with:

```python
    quiz.sources.set(source_ids)
```

- [ ] **Step 2: `fallback.py`**

Remove the `tag` parameter from all four functions. In `generate_flashcards_fallback` delete `tags=tag,`. In `generate_quiz_fallback` the description becomes `description='Basic quiz from document sections',`. `generate_quiz_fallback_multi` must link the real sources after the stand-in generates:

```python
def generate_quiz_fallback_multi(sources, user, question_count: int) -> Quiz:
    try:
        from ml.adapter import generate_quiz_ml
        return generate_quiz_ml(sources, user, question_count)
    except Exception:
        pass

    class _Combined:
        def __init__(self, title, text):
            self.title = title
            self.extracted_text = text

    label = sources[0].title if len(sources) == 1 else f'{len(sources)} documents'
    combined = _Combined(label, _combined_text(sources))
    quiz = generate_quiz_fallback(combined, user, question_count)
    # The stand-in has no id; the quiz is linked to the documents it stood for.
    quiz.sources.set([s.id for s in sources])
    return quiz
```

Flashcard fallbacks need nothing extra: `_replace_deck` links every deck.

- [ ] **Step 3: `ml/adapter.py`**

Remove `tag` from both signatures; delete `tags=tag,` in `generate_flashcards_ml`; in `generate_quiz_ml` the description line becomes `description=data.get("description") or "",` and add `quiz.sources.set([s.id for s in sources])` immediately after the `Quiz.objects.create(...)` call (before the questions loop, so a quiz that fails on questions and is deleted takes its links with it).

- [ ] **Step 4: `regeneration.py` — a replacement inherits its sources**

In `replace_card`, delete `tags=card.tags,` from the `Flashcard.objects.create(...)` call, and add directly after that call, still inside the `with transaction.atomic():` block:

```python
        # Inherited with the notebook: the replacement asks about the same
        # documents, and the study page scopes by them.
        replacement.sources.set(card.sources.all())
```

- [ ] **Step 5: Confirm no writer or reader of the tag remains in Python**

Run: `grep -rn "combined_source_tag\|SOURCE_TAG_PREFIX\|tags=\|tag_note\|, tag)" backend --include='*.py' | grep -v "/venv/\|/migrations/"`
Expected: nothing.

- [ ] **Step 6: Verify deck retirement directly, rolled back**

```bash
cd backend && ./venv/bin/python manage.py shell -c "
from django.db import transaction
from django.contrib.auth import get_user_model
from flashcards.models import Flashcard
from notebooks.models import Notebook
from notebooks.services.generate import _replace_deck
u = get_user_model().objects.get(id=2); nb = Notebook.objects.filter(user=u).first()
mk = lambda n: [Flashcard.objects.create(user=u, question=f'q{i}', answer='a') for i in range(n)]
class Rollback(Exception): pass
try:
    with transaction.atomic():
        other = mk(1); _replace_deck(other, u, [9, 11], nb)
        first = mk(2); _replace_deck(first, u, [9], nb)
        second = mk(2); _replace_deck(second, u, [9], nb)
        state = lambda cards: [Flashcard.objects.get(id=c.id).archived for c in cards]
        print('first deck archived :', state(first))
        print('second deck archived:', state(second))
        print('[9,11] deck archived:', state(other))
        print('second deck sources :', sorted(second[0].sources.values_list('id', flat=True)))
        raise Rollback
except Rollback: print('(rolled back)')
"
```
Expected:
```
first deck archived : [True, True]
second deck archived: [False, False]
[9,11] deck archived: [False]
second deck sources : [9]
```

- [ ] **Step 7: Suite and commit**

Run: `.venv/bin/pytest -q` — Expected: all pass.

```bash
git add backend/notebooks/services/generate.py backend/notebooks/services/fallback.py backend/ml/adapter.py backend/flashcards/services/regeneration.py
git commit -m "refactor(generate): link new cards and quizzes to their sources

_replace_deck now links the deck to its sources in the same transaction
that assigns its notebook and retires the previous deck; quizzes are
linked right after creation on every provider path. Nothing writes the
source:1,3 tag any more."
```

---

### Task 7: Drop the tag columns and the last references

**Files:**
- Modify: `backend/flashcards/models.py:8-24` (remove `tags`; fix the comment on `notebook`)
- Create: `backend/flashcards/migrations/0007_remove_flashcard_tags.py`
- Create: `backend/quizzes/migrations/0006_strip_source_tags_from_descriptions.py`
- Modify: `backend/flashcards/serializers.py` (drop `'tags'`), `backend/flashcards/views.py:13` (drop `'tags'` from `search_fields`)
- Modify: `docs/specs/2026-09-15-source-links-design.md` (status line)

- [ ] **Step 1: Remove the field and fix the comment**

In `backend/flashcards/models.py` delete the `tags = models.CharField(...)` line, and change the comment on `notebook` so its second and third lines read:

```python
    # The notebook this card was generated from. Cards used to be tied to their
    # notebook only by a `source:1,2` string, which meant deleting a
```

- [ ] **Step 2: Migrations**

`backend/flashcards/migrations/0007_remove_flashcard_tags.py`:

```python
"""The source tag lives in Flashcard.sources since 0006; nothing reads `tags`."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('flashcards', '0006_flashcard_sources')]

    operations = [
        migrations.RemoveField(model_name='flashcard', name='tags'),
    ]
```

`backend/quizzes/migrations/0006_strip_source_tags_from_descriptions.py`:

```python
"""Quiz descriptions carried a "[source:1,3]" suffix; the relation (0005) has
it now, so the description goes back to being a description."""
import re

from django.db import migrations

_SUFFIX = re.compile(r'\s*\[source:[\d,]+\]')


def strip_suffix(apps, schema_editor):
    Quiz = apps.get_model('quizzes', 'Quiz')
    for quiz in Quiz.objects.filter(description__contains='[source:'):
        quiz.description = _SUFFIX.sub('', quiz.description or '').strip()
        quiz.save(update_fields=['description'])


def restore_suffix(apps, schema_editor):
    Quiz = apps.get_model('quizzes', 'Quiz')
    for quiz in Quiz.objects.prefetch_related('sources'):
        ids = sorted(s.id for s in quiz.sources.all())
        if not ids:
            continue
        tag = f"[source:{','.join(map(str, ids))}]"
        if tag not in (quiz.description or ''):
            quiz.description = f"{quiz.description or ''} {tag}".strip()
            quiz.save(update_fields=['description'])


class Migration(migrations.Migration):
    dependencies = [('quizzes', '0005_quiz_sources')]

    operations = [migrations.RunPython(strip_suffix, restore_suffix)]
```

- [ ] **Step 3: Serializer and search field**

In `backend/flashcards/serializers.py` remove `'tags', ` from `fields`. In `backend/flashcards/views.py` change `search_fields = ['question', 'answer', 'tags']` to `search_fields = ['question', 'answer']`.

- [ ] **Step 4: Migrate and verify**

Run: `cd backend && ./venv/bin/python manage.py makemigrations --check --dry-run` — Expected: `No changes detected`.
Run: `./venv/bin/python manage.py migrate`
Then:

```bash
./venv/bin/python manage.py shell -c "
from quizzes.models import Quiz
from flashcards.models import Flashcard
print('descriptions still tagged:', Quiz.objects.filter(description__contains='[source:').count())
print('has tags attr:', hasattr(Flashcard, 'tags'))
print('links:', Flashcard.sources.through.objects.count(), Quiz.sources.through.objects.count())
"
```
Expected: `descriptions still tagged: 0`, `has tags attr: False`, `links: 20 5`.

- [ ] **Step 5: Last grep, full suite, typecheck**

Run:
```bash
grep -rn "source:\|\btags\b" backend --include='*.py' | grep -v "/venv/\|/migrations/"
grep -rn "\btags\b" app components lib
.venv/bin/pytest -q
./node_modules/.bin/tsc --noEmit -p tsconfig.json
```
Expected: both greps empty (a `source:` inside prose in a docstring is acceptable only if it describes history — read each hit); suite all green; `tsc` silent.

- [ ] **Step 6: Update the spec status and commit**

In the spec, change `**Status:** Approved (design), pending implementation plan` to `**Status:** Implemented 2026-09-15`.

```bash
git add backend/flashcards/models.py backend/flashcards/migrations/0007_remove_flashcard_tags.py backend/quizzes/migrations/0006_strip_source_tags_from_descriptions.py backend/flashcards/serializers.py backend/flashcards/views.py docs/specs/2026-09-15-source-links-design.md
git commit -m "refactor(sources): drop the source tag column and description suffix

Flashcard.tags is gone and quiz descriptions are descriptions again.
Provenance lives only in Flashcard.sources / Quiz.sources."
```

- [ ] **Step 7: Smoke the whole loop in the browser**

With `pnpm dev:all`: notebook → select two sources → Generate flashcards → workspace count updates → "Study" → cards listed → grade one → Analytics "By notebook" reflects it. Generate again from the same selection → count unchanged (old deck retired). Report what you saw, including anything that did not match.
