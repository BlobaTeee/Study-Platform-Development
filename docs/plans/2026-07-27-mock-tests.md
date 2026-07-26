# Mock Tests Implementation Plan

**Goal:** Let a student sit a timed paper drawn from a whole notebook — weighted toward material they answer badly — either now or at a time they plan in advance, with a reminder email.

**Architecture:** Sampling, reminder selection, and email composition live in Django-free modules under `backend/quizzes/services/`, unit-tested from `tests/` with no database. Three new models keep the existing quiz flow untouched. The paper is frozen at start so a refresh cannot reshuffle it, the clock is enforced server-side because a client timer is trivially bypassed, and reminders are sent by an idempotent management command a scheduler runs — the project has no task queue.

**Tech Stack:** Django 5.2, Django REST Framework, PostgreSQL, `django.core.mail` over SMTP, pytest (pure unit tests), Next.js 16 / React 19 / TypeScript.

## Global Constraints

- **No new runtime dependencies.** No Celery, RQ, or threads.
- **Tests must not require a database.** The project's Postgres role cannot create a test database (`permission denied to create database`). Every test here is a pure unit test in `tests/`, loading the module under test standalone via `importlib.util.spec_from_file_location`. Do **not** write Django `TestCase`s and do **not** create `backend/__init__.py`.
- **Migrations must be reversible** and must not rewrite historical rows. `makemigrations` in this project also proposes a pre-existing unrelated `AlterField` on `id` columns (`DEFAULT_AUTO_FIELD` drift) — leave that out of your migration.
- **Index every new query path** using the existing `Meta.indexes` convention.
- **The clock is server-authoritative.** The client may render a countdown; it may never decide whether an answer is in time.
- **No feedback until submission.** Answer responses must not leak `is_correct` or `correct_answer` — that is the whole difference between a test and a quiz.
- Reminder sending must be **idempotent**: running the command twice must not send twice.
- Email credentials come from `backend/.env` (gitignored) and must be a provider **app password**, never an account password. `.env.example` carries the keys with empty values.
- `quizzes` must not import `notebooks` at module level — `notebooks/views.py` already imports `quizzes.serializers`, so a module-level import back would be circular. Use the string form `'notebooks.Notebook'` in the ForeignKey.
- Run pytest with `./.venv/bin/python -m pytest` from the repo root; Django commands with `backend/venv/bin/python manage.py` from `backend/`.
- Comment style explains *why*, not *what*.
- Do not touch `ml_pipeline/answer_scorer.py` — it carries an intentional uncommitted edit.

**Natural stopping point:** after Task 4 the take-a-test-now half is complete and usable. Tasks 5–6 add planning and reminders; Tasks 7–8 add the UI.

---

### Task 1: Models and migration

**Files:**
- Modify: `backend/quizzes/models.py`
- Create: `backend/quizzes/migrations/0003_mock_tests.py` (generated, then hand-trimmed)

**Interfaces:**
- Consumes: existing `Question` model in the same file; `notebooks.Notebook` by string reference.
- Produces: `MockTest`, `MockTestQuestion`, `PlannedTest`. All later tasks use them.

- [ ] **Step 1: Add the three models**

Append to `backend/quizzes/models.py`:

```python
class MockTest(models.Model):
    """One sitting of a timed paper drawn from across a notebook.

    Separate from QuizAttempt, which is tied to a single Quiz by a non-null FK:
    a mock test deliberately spans every quiz in a notebook, so it needs its own
    record rather than a widened attempt.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mock_tests')
    # String reference on purpose: notebooks already imports quizzes.serializers,
    # so importing notebooks here would close a circular import.
    notebook = models.ForeignKey('notebooks.Notebook', on_delete=models.CASCADE,
                                 related_name='mock_tests')
    question_count = models.PositiveSmallIntegerField(default=20)
    duration_minutes = models.PositiveSmallIntegerField(default=30)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [models.Index(fields=['user', '-started_at'])]

    def __str__(self):
        return f'{self.user.username} — {self.notebook_id} ({self.question_count}q)'

    @property
    def deadline(self):
        """When the paper stops accepting answers."""
        from datetime import timedelta
        return self.started_at + timedelta(minutes=self.duration_minutes)


class MockTestQuestion(models.Model):
    """The frozen paper, and the answer given to each question.

    Freezing matters: without stored rows a refresh would resample and hand the
    student a different paper mid-sitting.
    """
    mock_test = models.ForeignKey(MockTest, on_delete=models.CASCADE, related_name='paper')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    order = models.PositiveSmallIntegerField()
    user_answer = models.TextField(blank=True, default='')
    # Null until submission — grading happens once, at the end.
    is_correct = models.BooleanField(null=True, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['order']
        unique_together = [('mock_test', 'order'), ('mock_test', 'question')]
        indexes = [models.Index(fields=['mock_test', 'order'])]

    def __str__(self):
        return f'{self.mock_test_id} #{self.order}'


class PlannedTest(models.Model):
    """A test the student intends to sit, and the state of its reminder."""
    REMINDER_CHOICES = [
        (1, '1 hour before'),
        (24, '1 day before'),
        (72, '3 days before'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='planned_tests')
    notebook = models.ForeignKey('notebooks.Notebook', on_delete=models.CASCADE,
                                 related_name='planned_tests')
    scheduled_for = models.DateTimeField()
    question_count = models.PositiveSmallIntegerField(default=20)
    duration_minutes = models.PositiveSmallIntegerField(default=30)
    reminder_lead_hours = models.PositiveSmallIntegerField(
        default=24, choices=REMINDER_CHOICES,
        help_text='How far ahead of the test the reminder goes out.')
    # Null until sent. This is the idempotency guard: the command stamps it
    # immediately, so a scheduler firing every few minutes cannot send twice.
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    mock_test = models.OneToOneField(MockTest, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='plan')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['scheduled_for']
        indexes = [
            # The reminder command's only query: unsent plans, by when they are due.
            models.Index(fields=['reminder_sent_at', 'scheduled_for']),
            models.Index(fields=['user', 'scheduled_for']),
        ]

    def __str__(self):
        return f'{self.user.username} — {self.scheduled_for:%Y-%m-%d %H:%M}'
```

- [ ] **Step 2: Generate the migration**

```bash
cd backend && ./venv/bin/python manage.py makemigrations quizzes
```

Expected: a migration creating `MockTest`, `MockTestQuestion`, `PlannedTest` with their indexes. If it also contains `AlterField` operations on any `id` column, or migrations for other apps, those are pre-existing `DEFAULT_AUTO_FIELD` drift — remove them from the file, rename it to `0003_mock_tests.py`, and keep `dependencies` pointing at `quizzes`' previous migration plus `('notebooks', '0001_initial')` (the FK needs it).

- [ ] **Step 3: Apply and prove reversibility**

```bash
cd backend && ./venv/bin/python manage.py migrate quizzes
./venv/bin/python manage.py migrate quizzes 0002 && ./venv/bin/python manage.py migrate quizzes
```

Expected: applies, rolls back, re-applies, all without error. A migration that cannot roll back is a defect — fix it rather than proceeding.

- [ ] **Step 4: Confirm nothing else broke**

Run: `cd backend && ./venv/bin/python manage.py check`
Expected: no errors (the 9 pre-existing `W042` warnings are fine).

- [ ] **Step 5: Commit**

```bash
git add backend/quizzes/models.py backend/quizzes/migrations
git commit -m "feat(quizzes): models for mock tests and planned tests"
```

---

### Task 2: Paper sampling

The pure core: given the questions available and how well the student knows each source, choose the paper.

**Files:**
- Create: `backend/quizzes/services/__init__.py`
- Create: `backend/quizzes/services/paper.py`
- Create: `tests/test_mock_test_paper.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `source_accuracy(answer_rows: list[dict]) -> dict[int, float]` — percent correct per source id.
  - `source_weights(accuracy: dict[int, float]) -> dict[int, float]`
  - `question_weight(entry: dict, weights: dict[int, float]) -> float`
  - `sample_paper(pool: list[dict], weights: dict[int, float], count: int, seed=None) -> list[dict]`

  `pool` entries are `{"id": int, "source_ids": list[int]}`; `answer_rows` are `{"source_ids": list[int], "is_correct": bool}`. Task 3 calls `source_accuracy`, `source_weights` and `sample_paper`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mock_test_paper.py`:

```python
"""Choosing a mock test's paper: weighted toward what the student answers badly."""
import importlib.util
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "quizzes" / "services" / "paper.py")


def _load():
    spec = importlib.util.spec_from_file_location("paper_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


paper = _load()


def _pool(n, source_id=1):
    return [{"id": i, "source_ids": [source_id]} for i in range(1, n + 1)]


# ---- accuracy ---------------------------------------------------------------

def test_accuracy_is_a_percentage_per_source():
    rows = [
        {"source_ids": [1], "is_correct": True},
        {"source_ids": [1], "is_correct": False},
        {"source_ids": [2], "is_correct": True},
    ]
    assert paper.source_accuracy(rows) == {1: 50.0, 2: 100.0}


def test_an_answer_counts_for_every_source_it_came_from():
    rows = [{"source_ids": [1, 2], "is_correct": False}]
    assert paper.source_accuracy(rows) == {1: 0.0, 2: 0.0}


def test_sources_never_answered_are_absent_rather_than_zero():
    # Zero would read as "got it wrong", which is not the same as "not tried".
    assert paper.source_accuracy([]) == {}


# ---- weights ----------------------------------------------------------------

def test_a_weak_source_outweighs_a_strong_one():
    weights = paper.source_weights({1: 30.0, 2: 95.0})
    assert weights[1] > weights[2]


def test_a_middling_source_sits_between_them():
    weights = paper.source_weights({1: 30.0, 2: 70.0, 3: 95.0})
    assert weights[1] > weights[2] > weights[3]


def test_an_unknown_source_weighs_neutral():
    assert paper.question_weight({"source_ids": [99]}, {}) == paper.NEUTRAL_WEIGHT


def test_a_question_takes_the_weight_of_its_weakest_source():
    weights = {1: 1.5, 2: 0.6}
    assert paper.question_weight({"source_ids": [1, 2]}, weights) == 1.5


# ---- sampling ---------------------------------------------------------------

def test_it_returns_exactly_the_requested_count():
    assert len(paper.sample_paper(_pool(30), {}, count=20, seed=1)) == 20


def test_a_pool_smaller_than_the_request_yields_the_whole_pool():
    assert len(paper.sample_paper(_pool(5), {}, count=20, seed=1)) == 5


def test_no_question_appears_twice():
    chosen = paper.sample_paper(_pool(30), {}, count=20, seed=1)
    assert len({entry["id"] for entry in chosen}) == 20


def test_the_same_seed_gives_the_same_paper():
    a = paper.sample_paper(_pool(30), {}, count=10, seed=7)
    b = paper.sample_paper(_pool(30), {}, count=10, seed=7)
    assert [e["id"] for e in a] == [e["id"] for e in b]


def test_different_seeds_give_different_papers():
    a = paper.sample_paper(_pool(40), {}, count=10, seed=1)
    b = paper.sample_paper(_pool(40), {}, count=10, seed=2)
    assert [e["id"] for e in a] != [e["id"] for e in b]


def test_weak_material_is_favoured_over_many_sittings():
    # One weak source, one strong, equal numbers of questions. Over enough
    # papers the weak source should supply clearly more of them — the point of
    # weighting. A single paper proves nothing, so this counts across many.
    pool = ([{"id": i, "source_ids": [1]} for i in range(1, 21)]
            + [{"id": i, "source_ids": [2]} for i in range(21, 41)])
    weights = paper.source_weights({1: 20.0, 2: 95.0})
    weak = 0
    for seed in range(60):
        chosen = paper.sample_paper(pool, weights, count=10, seed=seed)
        weak += sum(1 for e in chosen if e["source_ids"] == [1])
    assert weak > 60 * 10 * 0.5


def test_an_empty_pool_is_an_empty_paper():
    assert paper.sample_paper([], {}, count=10, seed=1) == []


def test_a_zero_or_negative_count_is_an_empty_paper():
    assert paper.sample_paper(_pool(10), {}, count=0, seed=1) == []
    assert paper.sample_paper(_pool(10), {}, count=-5, seed=1) == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_mock_test_paper.py -v`
Expected: FAIL — `spec_from_file_location` cannot find `paper.py`.

- [ ] **Step 3: Write the module**

```bash
mkdir -p backend/quizzes/services && touch backend/quizzes/services/__init__.py
```

Create `backend/quizzes/services/paper.py`:

```python
"""Choosing which questions make up a mock test.

A paper is drawn from every question a notebook's documents produced, weighted
so material the student answers badly turns up more often. Weighting rather than
selecting keeps a paper varied: a weak topic is likelier, never guaranteed, so
two sittings are not the same test.

No Django imports — the caller passes plain dicts, so the arithmetic and the
sampling stay unit-testable without a database.
"""
from __future__ import annotations

import random

#: Accuracy (percent) below which a document counts as weak, and above which it
#: counts as known. Mirrors the thresholds the recommendation engine already
#: uses, so the app does not disagree with itself about what "weak" means.
WEAK_ACCURACY = 60.0
STRONG_ACCURACY = 85.0

WEAK_WEIGHT = 1.5
NEUTRAL_WEIGHT = 1.0
STRONG_WEIGHT = 0.6


def source_accuracy(answer_rows: list[dict]) -> dict[int, float]:
    """Percent correct per source, from graded quiz answers.

    A source the student has never answered is absent rather than 0.0: zero
    would read as "got it wrong", which would push untouched material to the
    front of every paper.
    """
    totals: dict[int, list[int]] = {}
    for row in answer_rows:
        for sid in row.get("source_ids") or []:
            bucket = totals.setdefault(sid, [0, 0])
            bucket[0] += 1 if row.get("is_correct") else 0
            bucket[1] += 1
    return {sid: round(correct / total * 100, 1)
            for sid, (correct, total) in totals.items() if total}


def source_weights(accuracy: dict[int, float]) -> dict[int, float]:
    """Sampling weight per source: weak material weighs more."""
    weights = {}
    for sid, pct in accuracy.items():
        if pct < WEAK_ACCURACY:
            weights[sid] = WEAK_WEIGHT
        elif pct >= STRONG_ACCURACY:
            weights[sid] = STRONG_WEIGHT
        else:
            weights[sid] = NEUTRAL_WEIGHT
    return weights


def question_weight(entry: dict, weights: dict[int, float]) -> float:
    """A question weighs as much as the weakest source it came from.

    Taking the maximum means a question spanning a known and an unknown document
    is treated as worth asking, which is the cautious way round.
    """
    sids = entry.get("source_ids") or []
    if not sids:
        return NEUTRAL_WEIGHT
    return max(weights.get(sid, NEUTRAL_WEIGHT) for sid in sids)


def sample_paper(pool: list[dict], weights: dict[int, float], count: int,
                 seed=None) -> list[dict]:
    """`count` questions drawn from `pool` without replacement, weighted.

    Uses the Efraimidis–Spirakis key: each entry gets ``u ** (1 / w)`` for a
    uniform ``u``, and the largest keys win. Heavier entries push their keys
    toward 1, so they are likelier without ever being certain — and drawing by
    key rather than by repeated choice guarantees no question is asked twice.

    `seed` makes a paper reproducible, which is what lets the weighting be
    tested at all.
    """
    if count <= 0 or not pool:
        return []

    rng = random.Random(seed)
    scored = []
    for entry in pool:
        weight = max(question_weight(entry, weights), 1e-9)
        scored.append((rng.random() ** (1.0 / weight), entry))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [entry for _key, entry in scored[:count]]
```

- [ ] **Step 4: Run to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_mock_test_paper.py -v`
Expected: PASS, 15 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/quizzes/services tests/test_mock_test_paper.py
git commit -m "feat(quizzes): sample a mock test paper weighted to weak material"
```

---

### Task 3: Start a mock test

**Files:**
- Modify: `backend/quizzes/serializers.py`
- Modify: `backend/quizzes/views.py`
- Modify: `backend/quizzes/urls.py`

**Interfaces:**
- Consumes: `MockTest`, `MockTestQuestion` (Task 1); `source_accuracy`, `source_weights`, `sample_paper` (Task 2); `analytics.insights.parse_source_ids` (existing).
- Produces: `POST /api/quizzes/mock-tests/` creating a sitting, `GET /api/quizzes/mock-tests/{id}/` returning the paper without answers. Task 4 adds answering and submission.

- [ ] **Step 1: Add the serializers**

Append to `backend/quizzes/serializers.py`:

```python
class MockTestQuestionSerializer(serializers.ModelSerializer):
    """A question as it appears *during* the test — no answer, no marking.

    Withholding `correct_answer` and `is_correct` here is what separates a test
    from a quiz; the review serializer supplies them once the paper is handed in.
    """
    question_text = serializers.CharField(source='question.question_text', read_only=True)
    options = serializers.JSONField(source='question.options', read_only=True)

    class Meta:
        model = MockTestQuestion
        fields = ['id', 'order', 'question_text', 'options', 'user_answer']
        read_only_fields = fields


class MockTestQuestionReviewSerializer(serializers.ModelSerializer):
    """The same question after submission, with the marking revealed."""
    question_text = serializers.CharField(source='question.question_text', read_only=True)
    options = serializers.JSONField(source='question.options', read_only=True)
    correct_answer = serializers.CharField(source='question.correct_answer', read_only=True)
    explanation = serializers.CharField(source='question.explanation', read_only=True)

    class Meta:
        model = MockTestQuestion
        fields = ['id', 'order', 'question_text', 'options', 'user_answer',
                  'correct_answer', 'explanation', 'is_correct']
        read_only_fields = fields


class MockTestSerializer(serializers.ModelSerializer):
    paper = MockTestQuestionSerializer(many=True, read_only=True)
    notebook_title = serializers.CharField(source='notebook.title', read_only=True)
    deadline = serializers.DateTimeField(read_only=True)

    class Meta:
        model = MockTest
        fields = ['id', 'notebook', 'notebook_title', 'question_count',
                  'duration_minutes', 'started_at', 'deadline', 'completed_at',
                  'score', 'paper']
        read_only_fields = ['started_at', 'completed_at', 'score', 'paper']


class PlannedTestSerializer(serializers.ModelSerializer):
    notebook_title = serializers.CharField(source='notebook.title', read_only=True)

    class Meta:
        model = PlannedTest
        fields = ['id', 'notebook', 'notebook_title', 'scheduled_for',
                  'question_count', 'duration_minutes', 'reminder_lead_hours',
                  'reminder_sent_at', 'mock_test', 'created_at']
        read_only_fields = ['reminder_sent_at', 'mock_test', 'created_at']

    def validate_scheduled_for(self, value):
        from django.utils import timezone
        if value <= timezone.now():
            raise serializers.ValidationError('Pick a time in the future.')
        return value
```

Update the import at the top of the file:

```python
from .models import (
    Quiz, Question, QuizAttempt, Answer, MockTest, MockTestQuestion, PlannedTest,
)
```

- [ ] **Step 2: Add the viewset**

Append to `backend/quizzes/views.py`:

```python
class MockTestViewSet(viewsets.ModelViewSet):
    """Sit a timed paper drawn from a whole notebook."""
    serializer_class = MockTestSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        return (MockTest.objects.filter(user=self.request.user)
                .select_related('notebook')
                .prefetch_related('paper__question'))

    def create(self, request, *args, **kwargs):
        from notebooks.models import Notebook

        notebook = Notebook.objects.filter(
            id=request.data.get('notebook'), user=request.user).first()
        if notebook is None:
            return Response({'detail': 'Notebook not found.'}, status=404)

        requested = int(request.data.get('question_count', 20))
        duration = int(request.data.get('duration_minutes', 30))
        pool = _question_pool(request.user, notebook)
        if not pool:
            return Response(
                {'detail': 'No quiz questions for this notebook yet. '
                           'Generate a quiz from its documents first.'},
                status=400,
            )

        weights = source_weights(_source_accuracy(request.user))
        chosen = sample_paper(pool, weights, count=requested)

        test = MockTest.objects.create(
            user=request.user, notebook=notebook,
            question_count=len(chosen), duration_minutes=duration,
        )
        MockTestQuestion.objects.bulk_create([
            MockTestQuestion(mock_test=test, question_id=entry['id'], order=i)
            for i, entry in enumerate(chosen)
        ])

        test.refresh_from_db()
        data = MockTestSerializer(test).data
        # Say so rather than silently handing over a shorter paper: the student
        # is about to judge their readiness on it.
        if len(chosen) < requested:
            data['short_paper'] = True
        return Response(data, status=status.HTTP_201_CREATED)
```

Add these helpers above the class:

```python
def _question_pool(user, notebook):
    """Every question generated from this notebook's documents.

    Source ids are parsed out of the quiz description rather than matched as a
    substring: `source:3` is a prefix of `source:30`, so substring matching
    would quietly mix in another document's questions.
    """
    from analytics import insights

    source_ids = set(notebook.sources.values_list('id', flat=True))
    if not source_ids:
        return []

    pool = []
    for row in Question.objects.filter(quiz__user=user).values('id', 'quiz__description'):
        matched = [sid for sid in insights.parse_source_ids(row['quiz__description'])
                   if sid in source_ids]
        if matched:
            pool.append({'id': row['id'], 'source_ids': matched})
    return pool


def _source_accuracy(user):
    """How well the user has answered questions from each document so far."""
    from analytics import insights

    rows = [
        {'source_ids': insights.parse_source_ids(row['question__quiz__description']),
         'is_correct': row['is_correct']}
        for row in Answer.objects.filter(quiz_attempt__user=user)
        .values('question__quiz__description', 'is_correct')
    ]
    return source_accuracy(rows)
```

Update the imports at the top of `views.py`:

```python
from .models import (
    Quiz, Question, QuizAttempt, Answer, MockTest, MockTestQuestion, PlannedTest,
)
from .serializers import (
    QuizSerializer, QuestionSerializer, QuizAttemptSerializer, AnswerSerializer,
    MockTestSerializer, MockTestQuestionReviewSerializer, PlannedTestSerializer,
)
from .services.paper import sample_paper, source_accuracy, source_weights
```

- [ ] **Step 3: Register the route**

In `backend/quizzes/urls.py`:

```python
from .views import (
    QuizViewSet, QuestionViewSet, QuizAttemptViewSet, MockTestViewSet,
)

router.register(r'mock-tests', MockTestViewSet, basename='mock-test')
```

- [ ] **Step 4: Verify it loads and the route exists**

```bash
cd backend && ./venv/bin/python manage.py check
./venv/bin/python manage.py shell -c "from django.urls import reverse; print(reverse('mock-test-list'))"
```
Expected: check clean apart from the pre-existing `W042` warnings; the reverse prints `/api/quizzes/mock-tests/`.

- [ ] **Step 5: Run the suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/quizzes/serializers.py backend/quizzes/views.py backend/quizzes/urls.py
git commit -m "feat(quizzes): start a mock test with a frozen, weighted paper"
```

---

### Task 4: Answer and submit, with a server-enforced clock

**Files:**
- Create: `backend/quizzes/services/timing.py`
- Create: `tests/test_mock_test_timing.py`
- Modify: `backend/quizzes/views.py`

**Interfaces:**
- Consumes: `MockTest`, `MockTestQuestion` (Task 1).
- Produces: `answers_are_open(started_at, duration_minutes, now) -> bool`; `POST /api/quizzes/mock-tests/{id}/answer/` and `POST /api/quizzes/mock-tests/{id}/submit/`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_mock_test_timing.py`:

```python
"""Whether a mock test is still accepting answers."""
import importlib.util
from datetime import datetime, timedelta, timezone as tz
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "quizzes" / "services" / "timing.py")


def _load():
    spec = importlib.util.spec_from_file_location("timing_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


timing = _load()
START = datetime(2026, 7, 27, 10, 0, tzinfo=tz.utc)


def test_answers_are_open_at_the_start():
    assert timing.answers_are_open(START, 30, START) is True


def test_answers_are_open_just_before_the_deadline():
    assert timing.answers_are_open(START, 30, START + timedelta(minutes=29, seconds=59)) is True


def test_answers_close_exactly_at_the_deadline():
    # The deadline is the end of the allowed time, not one more second of it.
    assert timing.answers_are_open(START, 30, START + timedelta(minutes=30)) is False


def test_answers_are_closed_after_the_deadline():
    assert timing.answers_are_open(START, 30, START + timedelta(minutes=31)) is False


def test_a_zero_duration_test_is_never_open():
    assert timing.answers_are_open(START, 0, START) is False


def test_seconds_remaining_never_goes_negative():
    assert timing.seconds_remaining(START, 30, START + timedelta(minutes=99)) == 0


def test_seconds_remaining_counts_down():
    assert timing.seconds_remaining(START, 30, START + timedelta(minutes=10)) == 1200
```

- [ ] **Step 2: Run to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_mock_test_timing.py -v`
Expected: FAIL — `timing.py` does not exist.

- [ ] **Step 3: Write the module**

Create `backend/quizzes/services/timing.py`:

```python
"""Whether a mock test's clock has run out.

Kept separate from the view and free of Django so the boundary condition — the
one thing a timed test must get right — can be tested directly. The client
renders a countdown, but only this decides whether an answer arrived in time:
a timer in the browser is changed by anyone who opens the developer tools.
"""
from __future__ import annotations

from datetime import timedelta


def deadline_for(started_at, duration_minutes: int):
    """When the paper stops accepting answers."""
    return started_at + timedelta(minutes=duration_minutes)


def answers_are_open(started_at, duration_minutes: int, now) -> bool:
    """True while the paper is still within its allotted time.

    The deadline itself is closed: a test with thirty minutes gets thirty
    minutes, not thirty minutes and one more answer.
    """
    return now < deadline_for(started_at, duration_minutes)


def seconds_remaining(started_at, duration_minutes: int, now) -> int:
    """Whole seconds left, never negative — an overrun is simply out of time."""
    remaining = (deadline_for(started_at, duration_minutes) - now).total_seconds()
    return max(0, int(remaining))
```

- [ ] **Step 4: Run to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_mock_test_timing.py -v`
Expected: PASS, 7 passed.

- [ ] **Step 5: Add the answer and submit actions**

Add to `MockTestViewSet` in `backend/quizzes/views.py`:

```python
    @action(detail=True, methods=['post'])
    def answer(self, request, pk=None):
        """Record one answer. Deliberately returns no marking.

        Telling the student whether they were right would turn the paper back
        into a quiz, so the response carries only what is needed to keep going.
        """
        from django.utils import timezone
        from .services.timing import answers_are_open, seconds_remaining

        test = self.get_object()
        if test.completed_at:
            return Response({'detail': 'This test has already been submitted.'}, status=400)

        now = timezone.now()
        if not answers_are_open(test.started_at, test.duration_minutes, now):
            return Response({'detail': 'Time is up for this test.',
                             'seconds_remaining': 0}, status=409)

        row = test.paper.filter(id=request.data.get('paper_question_id')).first()
        if row is None:
            return Response({'detail': 'Question not part of this test.'}, status=404)

        row.user_answer = str(request.data.get('answer', ''))
        row.answered_at = now
        row.save(update_fields=['user_answer', 'answered_at'])

        return Response({
            'id': row.id,
            'answered': True,
            'seconds_remaining': seconds_remaining(
                test.started_at, test.duration_minutes, now),
        })

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        """Grade the whole paper and hand back the full review."""
        from django.db import transaction
        from django.utils import timezone

        test = self.get_object()
        if test.completed_at:
            return Response(self._review(test))

        rows = list(test.paper.select_related('question'))
        # Grading and stamping must land together, or a crash between them would
        # leave a paper that reads as unfinished but is already marked.
        with transaction.atomic():
            correct = 0
            for row in rows:
                row.is_correct = (row.user_answer or '').strip() == \
                    (row.question.correct_answer or '').strip()
                correct += 1 if row.is_correct else 0
            MockTestQuestion.objects.bulk_update(rows, ['is_correct'])

            test.completed_at = timezone.now()
            test.score = round(correct / len(rows) * 100, 1) if rows else 0.0
            test.save(update_fields=['completed_at', 'score'])

        return Response(self._review(test))

    def _review(self, test):
        """The paper with its marking revealed — only ever after submission."""
        rows = test.paper.select_related('question').all()
        return {
            'id': test.id,
            'score': test.score,
            'completed_at': test.completed_at,
            'question_count': test.question_count,
            'correct_count': sum(1 for r in rows if r.is_correct),
            'paper': MockTestQuestionReviewSerializer(rows, many=True).data,
        }
```

- [ ] **Step 6: Run the suite and the checks**

```bash
./.venv/bin/python -m pytest -q
cd backend && ./venv/bin/python manage.py check
```
Expected: all pass; check clean apart from the pre-existing `W042` warnings.

- [ ] **Step 7: Commit**

```bash
git add backend/quizzes/services/timing.py backend/quizzes/views.py tests/test_mock_test_timing.py
git commit -m "feat(quizzes): answer and submit a mock test on a server-held clock"
```

---

### Task 5: Email configuration and the reminder message

**Files:**
- Modify: `backend/studyplatform/settings.py`
- Modify: `backend/.env.example`
- Create: `backend/quizzes/services/reminder_email.py`
- Create: `tests/test_reminder_email.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `build_reminder(notebook_title: str, scheduled_for, question_count: int, duration_minutes: int, url: str) -> tuple[str, str]` returning `(subject, body)`. Task 6 sends it.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reminder_email.py`:

```python
"""The reminder email's wording."""
import importlib.util
from datetime import datetime
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "quizzes" / "services" / "reminder_email.py")


def _load():
    spec = importlib.util.spec_from_file_location("reminder_email_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


emails = _load()
WHEN = datetime(2026, 7, 30, 14, 0)


def _build():
    return emails.build_reminder(
        notebook_title="Biology",
        scheduled_for=WHEN,
        question_count=20,
        duration_minutes=30,
        url="http://localhost:3000/dashboard/tests",
    )


def test_the_subject_names_the_subject_studied():
    subject, _ = _build()
    assert "Biology" in subject


def test_the_subject_is_a_single_line():
    subject, _ = _build()
    assert "\n" not in subject


def test_the_body_carries_the_time_length_and_link():
    _, body = _build()
    assert "30 minutes" in body
    assert "20 questions" in body
    assert "http://localhost:3000/dashboard/tests" in body


def test_the_body_states_the_scheduled_day_and_time():
    _, body = _build()
    assert "30 July 2026" in body
    assert "14:00" in body


def test_the_wording_stays_plain():
    # The app's voice is calm and scholarly; a reminder must not nag or shout.
    subject, body = _build()
    assert "!" not in subject and "!" not in body
```

- [ ] **Step 2: Run to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_reminder_email.py -v`
Expected: FAIL — `reminder_email.py` does not exist.

- [ ] **Step 3: Write the module**

Create `backend/quizzes/services/reminder_email.py`:

```python
"""Wording for the planned-test reminder.

Free of Django so the message can be tested without a mail backend, and so the
command that sends it stays a thin shell around this.
"""
from __future__ import annotations


def build_reminder(notebook_title: str, scheduled_for, question_count: int,
                   duration_minutes: int, url: str) -> tuple[str, str]:
    """The (subject, body) of a reminder for one planned test.

    Plain and specific: the student booked this themselves, so the mail only
    has to say what and when, and get out of the way.
    """
    when = scheduled_for.strftime('%d %B %Y at %H:%M').lstrip('0')
    subject = f'Your {notebook_title} mock test is coming up'
    body = (
        f'You planned a mock test on {notebook_title}.\n\n'
        f'When: {when}\n'
        f'Paper: {question_count} questions, {duration_minutes} minutes\n\n'
        f'Sit it here: {url}\n\n'
        f'— StudyFlow\n'
    )
    return subject, body
```

- [ ] **Step 4: Run to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_reminder_email.py -v`
Expected: PASS, 5 passed.

- [ ] **Step 5: Add the email settings**

Append to `backend/studyplatform/settings.py`, after the `SUPABASE_URL` line:

```python
# --- Email (planned-test reminders) ---
# Real SMTP. The credential must be a provider *app password*, never an account
# password, and lives in backend/.env, which is gitignored. With EMAIL_HOST
# unset the console backend is used instead, so a developer without credentials
# still sees exactly what would have been sent rather than hitting an error.
EMAIL_HOST = config('EMAIL_HOST', default='')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL',
                            default='StudyFlow <no-reply@studyflow.local>')
EMAIL_BACKEND = config(
    'EMAIL_BACKEND',
    default=('django.core.mail.backends.smtp.EmailBackend' if EMAIL_HOST
             else 'django.core.mail.backends.console.EmailBackend'),
)

# Where a reminder tells the student to go to sit their test.
FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:3000').rstrip('/')
```

- [ ] **Step 6: Document the keys**

Append to `backend/.env.example`:

```
# --- Email (planned-test reminders) ---
# Leave EMAIL_HOST empty to print reminders to the console instead of sending.
# Use a provider APP PASSWORD, never your account password.
EMAIL_HOST=
EMAIL_PORT=587
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=StudyFlow <no-reply@studyflow.local>

# Base URL the reminder links back to.
FRONTEND_URL=http://localhost:3000
```

- [ ] **Step 7: Verify settings load**

```bash
cd backend && ./venv/bin/python manage.py check
./venv/bin/python manage.py shell -c "from django.conf import settings; print(settings.EMAIL_BACKEND)"
```
Expected: check clean; with no `EMAIL_HOST` set it prints the console backend.

- [ ] **Step 8: Commit**

```bash
git add backend/studyplatform/settings.py backend/.env.example backend/quizzes/services/reminder_email.py tests/test_reminder_email.py
git commit -m "feat(quizzes): email settings and the planned-test reminder wording"
```

---

### Task 6: Planned tests and the reminder command

**Files:**
- Create: `backend/quizzes/services/reminders.py`
- Create: `tests/test_test_reminders.py`
- Create: `backend/quizzes/management/__init__.py`
- Create: `backend/quizzes/management/commands/__init__.py`
- Create: `backend/quizzes/management/commands/send_test_reminders.py`
- Modify: `backend/quizzes/views.py`, `backend/quizzes/urls.py`

**Interfaces:**
- Consumes: `PlannedTest` (Task 1); `build_reminder` (Task 5).
- Produces: `due_reminders(plans: list[dict], now) -> list[dict]`; the `send_test_reminders` command; `/api/quizzes/planned-tests/`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_test_reminders.py`:

```python
"""Which planned tests are owed a reminder right now."""
import importlib.util
from datetime import datetime, timedelta, timezone as tz
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "quizzes" / "services" / "reminders.py")


def _load():
    spec = importlib.util.spec_from_file_location("reminders_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


reminders = _load()
NOW = datetime(2026, 7, 27, 12, 0, tzinfo=tz.utc)


def _plan(**overrides):
    plan = {
        "id": 1,
        "scheduled_for": NOW + timedelta(hours=24),
        "reminder_lead_hours": 24,
        "reminder_sent_at": None,
        "taken": False,
    }
    plan.update(overrides)
    return plan


def test_a_plan_exactly_at_its_lead_time_is_due():
    # 24h ahead with a 24h lead: the window opens now, to the second.
    assert [p["id"] for p in reminders.due_reminders([_plan()], NOW)] == [1]


def test_a_plan_still_beyond_its_lead_time_is_not_due():
    plan = _plan(scheduled_for=NOW + timedelta(hours=25))
    assert reminders.due_reminders([plan], NOW) == []


def test_a_plan_inside_its_lead_time_is_due():
    plan = _plan(scheduled_for=NOW + timedelta(hours=2))
    assert [p["id"] for p in reminders.due_reminders([plan], NOW)] == [1]


def test_a_plan_already_reminded_is_skipped():
    plan = _plan(reminder_sent_at=NOW - timedelta(hours=1))
    assert reminders.due_reminders([plan], NOW) == []


def test_a_plan_already_sat_is_skipped():
    assert reminders.due_reminders([_plan(taken=True)], NOW) == []


def test_a_test_whose_time_has_passed_is_skipped():
    # Reminding someone about a test they have already missed is noise.
    plan = _plan(scheduled_for=NOW - timedelta(minutes=1))
    assert reminders.due_reminders([plan], NOW) == []


def test_a_short_lead_holds_the_reminder_back():
    plan = _plan(scheduled_for=NOW + timedelta(hours=5), reminder_lead_hours=1)
    assert reminders.due_reminders([plan], NOW) == []
    later = NOW + timedelta(hours=4, minutes=1)
    assert [p["id"] for p in reminders.due_reminders([plan], later)] == [1]


def test_several_plans_are_filtered_independently():
    plans = [
        _plan(id=1),
        _plan(id=2, reminder_sent_at=NOW),
        _plan(id=3, scheduled_for=NOW + timedelta(days=9)),
    ]
    assert [p["id"] for p in reminders.due_reminders(plans, NOW)] == [1]
```

- [ ] **Step 2: Run to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_test_reminders.py -v`
Expected: FAIL — `reminders.py` does not exist.

- [ ] **Step 3: Write the module**

Create `backend/quizzes/services/reminders.py`:

```python
"""Deciding which planned tests are owed a reminder.

Pulled out of the management command so the rule can be tested without a
database, a mail backend, or a real clock — the three things that make
scheduled sending awkward to verify otherwise.
"""
from __future__ import annotations

from datetime import timedelta


def due_reminders(plans: list[dict], now) -> list[dict]:
    """The plans whose reminder should go out at `now`.

    A plan qualifies once its lead time has opened, provided nothing has been
    sent yet and the test has neither been sat nor already passed. Reminding
    someone about a test that has come and gone is noise, so those are dropped
    rather than sent late.

    Callers stamp `reminder_sent_at` after sending, which is what makes running
    this on a short schedule safe: an already-reminded plan can never qualify a
    second time.
    """
    due = []
    for plan in plans:
        if plan.get("reminder_sent_at") is not None or plan.get("taken"):
            continue
        scheduled = plan["scheduled_for"]
        if scheduled <= now:
            continue
        lead = timedelta(hours=plan.get("reminder_lead_hours") or 0)
        if scheduled - lead <= now:
            due.append(plan)
    return due
```

- [ ] **Step 4: Run to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_test_reminders.py -v`
Expected: PASS, 8 passed.

- [ ] **Step 5: Write the command**

```bash
mkdir -p backend/quizzes/management/commands
touch backend/quizzes/management/__init__.py backend/quizzes/management/commands/__init__.py
```

Create `backend/quizzes/management/commands/send_test_reminders.py`:

```python
"""Send reminders for planned tests whose lead time has arrived.

Run on a schedule (cron or launchd), e.g. every fifteen minutes:

    */15 * * * * cd /path/to/backend && ./venv/bin/python manage.py send_test_reminders

Safe to run as often as you like: each plan's `reminder_sent_at` is stamped as
it is sent, so a second run finds nothing to do.
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from quizzes.models import PlannedTest
from quizzes.services.reminder_email import build_reminder
from quizzes.services.reminders import due_reminders


class Command(BaseCommand):
    help = 'Email reminders for planned tests whose lead time has arrived.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be sent without sending or stamping.')

    def handle(self, *args, **options):
        now = timezone.now()
        candidates = list(
            PlannedTest.objects.filter(reminder_sent_at__isnull=True)
            .select_related('user', 'notebook')
        )
        rows = [{
            'id': plan.id,
            'scheduled_for': plan.scheduled_for,
            'reminder_lead_hours': plan.reminder_lead_hours,
            'reminder_sent_at': plan.reminder_sent_at,
            'taken': plan.mock_test_id is not None,
        } for plan in candidates]

        by_id = {plan.id: plan for plan in candidates}
        due = [by_id[row['id']] for row in due_reminders(rows, now)]

        if not due:
            self.stdout.write('No reminders due.')
            return

        sent = 0
        for plan in due:
            recipient = (plan.user.email or '').strip()
            if not recipient:
                # Nothing to send to. Stamping anyway would silently swallow the
                # reminder, so it is left for when the account has an address.
                self.stderr.write(f'Plan {plan.id}: user has no email address; skipped.')
                continue

            subject, body = build_reminder(
                notebook_title=plan.notebook.title,
                scheduled_for=timezone.localtime(plan.scheduled_for),
                question_count=plan.question_count,
                duration_minutes=plan.duration_minutes,
                url=f'{settings.FRONTEND_URL}/dashboard/tests',
            )

            if options['dry_run']:
                self.stdout.write(f'Would send to {recipient}: {subject}')
                continue

            try:
                send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient])
            except Exception as exc:  # noqa: BLE001
                # One unreachable recipient must not abort the batch, and the
                # plan stays unstamped so the next run tries again.
                self.stderr.write(f'Plan {plan.id}: send failed ({exc}).')
                continue

            plan.reminder_sent_at = timezone.now()
            plan.save(update_fields=['reminder_sent_at'])
            sent += 1

        self.stdout.write(f'Sent {sent} reminder(s).')
```

- [ ] **Step 6: Add the planned-test API**

Append to `backend/quizzes/views.py`:

```python
class PlannedTestViewSet(viewsets.ModelViewSet):
    """Tests the student intends to sit, and their reminders."""
    serializer_class = PlannedTestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (PlannedTest.objects.filter(user=self.request.user)
                .select_related('notebook'))

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
```

Register it in `backend/quizzes/urls.py`:

```python
from .views import (
    QuizViewSet, QuestionViewSet, QuizAttemptViewSet, MockTestViewSet,
    PlannedTestViewSet,
)

router.register(r'planned-tests', PlannedTestViewSet, basename='planned-test')
```

- [ ] **Step 7: Verify the command runs**

```bash
cd backend && ./venv/bin/python manage.py send_test_reminders --dry-run
./venv/bin/python manage.py check
```
Expected: prints `No reminders due.` (nothing is planned yet) and exits 0; check clean apart from the pre-existing `W042` warnings.

- [ ] **Step 8: Run the suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/quizzes/services/reminders.py backend/quizzes/management backend/quizzes/views.py backend/quizzes/urls.py tests/test_test_reminders.py
git commit -m "feat(quizzes): plan a test and send its reminder from a command"
```

---

### Task 7: Frontend — sit a mock test

**Files:**
- Modify: `lib/api.ts`
- Create: `app/dashboard/tests/page.tsx`

**Interfaces:**
- Consumes: the endpoints from Tasks 3, 4 and 6.
- Produces: `mockTestsAPI` and `plannedTestsAPI` in `lib/api.ts`; Task 8 adds the planning form to the same page.

- [ ] **Step 1: Add the API client methods**

Append to `lib/api.ts`:

```typescript
export const mockTestsAPI = {
  // Starting a test freezes its paper server-side, so a refresh cannot reshuffle it.
  start: (data: { notebook: number; question_count?: number; duration_minutes?: number }) =>
    api.post('/quizzes/mock-tests/', data),
  get: (id: number) => api.get(`/quizzes/mock-tests/${id}/`),
  // Deliberately returns no marking — feedback waits until the paper is handed in.
  answer: (id: number, paperQuestionId: number, answer: string) =>
    api.post(`/quizzes/mock-tests/${id}/answer/`, {
      paper_question_id: paperQuestionId,
      answer,
    }),
  submit: (id: number) => api.post(`/quizzes/mock-tests/${id}/submit/`, {}),
}

export const plannedTestsAPI = {
  list: () => api.get('/quizzes/planned-tests/'),
  create: (data: {
    notebook: number
    scheduled_for: string
    question_count?: number
    duration_minutes?: number
    reminder_lead_hours?: number
  }) => api.post('/quizzes/planned-tests/', data),
  remove: (id: number) => api.delete(`/quizzes/planned-tests/${id}/`),
}
```

- [ ] **Step 2: Build the page**

Create `app/dashboard/tests/page.tsx`. It must follow the project's design system: the study-paper light theme, quizzes' violet mode colour (`bg-mode-quizzes`, `text-mode-quizzes`) since a test is an assessment, Fraunces headings via the existing type classes, and calm plain copy with no exclamation marks. Model its structure on `app/dashboard/quizzes/page.tsx`, which already handles picking a notebook and rendering questions — read that file first and reuse its patterns rather than inventing new ones.

The page has three states:

1. **Setup** — pick a notebook, question count (default 20) and duration (default 30 minutes), then a "Start test" button calling `mockTestsAPI.start`. If the response carries `short_paper: true`, show a quiet line saying the paper is shorter than asked because the notebook has fewer questions.
2. **Sitting** — one question at a time with its options, a countdown derived from the `deadline` field, and next/previous. Each answer posts via `mockTestsAPI.answer`. **Never render correctness here.** When the countdown reaches zero, or the API returns 409, stop accepting input and submit automatically.
3. **Review** — after `submit`, show the score, the correct/total count, and every question with the student's answer, the correct answer, and the explanation.

Requirements that are easy to get wrong:
- The countdown is display only. Trust the server: a 409 from `answer` means time is up regardless of what the countdown says.
- Compute remaining time from the server's `deadline`, not by counting down from the duration — a slow page load would otherwise hand out extra time.
- Honour `prefers-reduced-motion` on any transition, per the project's accessibility rules.
- The keyboard must work: options selectable and a visible focus ring.

- [ ] **Step 3: Typecheck**

Run: `npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add lib/api.ts app/dashboard/tests/page.tsx
git commit -m "feat(tests): sit a timed mock test"
```

---

### Task 8: Frontend — plan a test, and a way in

**Files:**
- Modify: `app/dashboard/tests/page.tsx`
- Modify: `components/dashboard-sidebar.tsx`

**Interfaces:**
- Consumes: `plannedTestsAPI` (Task 7).
- Produces: nothing other tasks depend on.

- [ ] **Step 1: Add the planning form and list**

In `app/dashboard/tests/page.tsx`, add a "Planned tests" section below the setup state containing:

- A form: notebook, date and time (an `<input type="datetime-local">`), question count, duration, and a reminder lead select with exactly three options — `1` ("1 hour before"), `24` ("1 day before", the default) and `72` ("3 days before"). These values must match the backend's `REMINDER_CHOICES` exactly.
- The list of upcoming planned tests from `plannedTestsAPI.list()`, each showing its notebook, when it is scheduled, the paper's shape, and whether its reminder has gone out (`reminder_sent_at`). Give each a "Start now" button that calls `mockTestsAPI.start` with that plan's notebook and shape, and a "Cancel" that calls `plannedTestsAPI.remove`.

Convert the `datetime-local` value to an ISO string before posting. A time in the past is rejected by the backend with a 400 on `scheduled_for`; surface that message rather than a generic failure.

- [ ] **Step 2: Add the sidebar link**

In `components/dashboard-sidebar.tsx`, add a "Tests" item pointing at `/dashboard/tests`, using the quizzes violet mode colour and matching the existing items' structure exactly — read the file and copy the shape of an existing entry rather than writing a new one.

- [ ] **Step 3: Typecheck**

Run: `npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 4: Verify the whole feature by hand**

With `pnpm dev:all` running:
1. Generate a quiz from a notebook's documents (mock tests need questions to draw from).
2. Start a test, answer some questions, and confirm **no correctness is shown** while sitting it.
3. Submit and confirm the score and full review appear.
4. Plan a test for a few minutes ahead with a 1-hour lead, then run `cd backend && ./venv/bin/python manage.py send_test_reminders` and confirm the reminder appears (in the console with no `EMAIL_HOST` set, or in your inbox with SMTP configured).
5. Run the command a second time and confirm it reports nothing due — proving idempotency.

- [ ] **Step 5: Commit**

```bash
git add app/dashboard/tests/page.tsx components/dashboard-sidebar.tsx
git commit -m "feat(tests): plan a test, and reach tests from the sidebar"
```

---

## Self-Review

**Spec coverage.** Every component in the spec maps to a task: the three models → Task 1; `sample_paper` with weak-topic weighting and sitting-time sampling → Tasks 2 and 3; the frozen paper, withheld feedback and server-authoritative deadline → Tasks 3 and 4; email configuration and `.env.example` keys → Task 5; `due_reminders`, the idempotent command and the planned-test API → Task 6; the UI for both modes → Tasks 7 and 8. Error handling from the spec is covered: an empty pool returns a clear message (Task 3), a short paper is flagged rather than silent (Task 3), a past `scheduled_for` fails validation (Task 3's serializer), SMTP failure leaves the plan unstamped for retry and does not abort the batch (Task 6), a late answer is rejected with 409 (Task 4), and starting a submitted test returns its review rather than a second paper (Task 4).

**Deviation from the spec, deliberate.** The spec said `EMAIL_BACKEND` would be real SMTP. The plan defaults to SMTP **when `EMAIL_HOST` is set** and the console backend otherwise, so a checkout without credentials prints reminders instead of raising. This keeps the user's "real SMTP now" decision — set the host and it sends for real — while making the feature runnable and testable without secrets.

**Two spec statements corrected while planning.** The spec described auto-submitting an abandoned test "on next access"; Task 4 instead grades whatever was recorded when `submit` is called and rejects late answers with 409, because a background sweep would need a scheduler this project does not have for that purpose. The spec's `per_source_mastery` reuse became a smaller, purpose-built `source_accuracy` in Task 2: the analytics function returns display rows (titles, card and question counts) that a sampler does not need, and depending on its shape would couple the two.

**Placeholder scan:** none. Tasks 7 and 8 describe UI behaviour rather than giving complete JSX, because the page must match `app/dashboard/quizzes/page.tsx`'s existing patterns and the project's design system; every value that must match the backend (reminder lead options, field names, endpoints) is given exactly.

**Type consistency.** `sample_paper(pool, weights, count, seed)` returns pool entries (dicts with `id`), and Task 3 reads `entry['id']` — consistent. `source_accuracy` returns percentages 0–100 and `source_weights` compares against `WEAK_ACCURACY = 60.0` / `STRONG_ACCURACY = 85.0` — consistent, and matching `analytics.insights`, which also reports accuracy as a percentage. `answers_are_open(started_at, duration_minutes, now)` and `seconds_remaining(...)` take the same three arguments in the same order at both call sites. `build_reminder(...)`'s five keyword arguments match the command's call exactly. `due_reminders` consumes dicts with `scheduled_for`, `reminder_lead_hours`, `reminder_sent_at` and `taken`, which is exactly what the command builds.

**Known constraint.** As with the flashcard work, the project's Postgres role cannot create a test database, so the models, viewsets, and the command's database interaction are verified by inspection and by the manual run in Task 8 Step 4. The pure cores — sampling, timing, reminder selection, and the message — are properly unit-tested, which is where the logic that can silently go wrong lives.
