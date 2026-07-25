# Flashcard Review Quality Implementation Plan

**Goal:** Make flashcard re-study test understanding rather than memorised wording — a card graded *Hard* is replaced by a newly generated question on the same concept — while capping a document at ten active cards and reducing the grade scale to three.

**Architecture:** Business logic goes in Django-free modules under `backend/*/services/` and `scheduling.py`, unit-tested from `tests/` with no database; Django models and views stay thin glue around them. Regeneration runs lazily when due cards are fetched, so grading stays instant and no worker process is required.

**Tech Stack:** Django 5.2, Django REST Framework, PostgreSQL, pytest (pure unit tests), Next.js 16 / React 19 / TypeScript frontend.

## Global Constraints

- **No new runtime dependencies.** No Celery, RQ, or threads; regeneration must run inside the existing request cycle.
- **Tests must not require a database.** The project's Postgres role cannot create the test database (`permission denied to create database`), so every test in this plan is a pure unit test under `tests/`. Extract logic into Django-free functions rather than writing `TestCase`s.
- **Cloud-free fallback.** Regeneration uses the configured local provider; on failure it falls back to deterministic reformatting, never to Gemini.
- **Migrations must be reversible** and must not rewrite historical rows.
- **Index every new query path** using the existing `Meta.indexes` convention.
- `MAX_CARDS_PER_SOURCE = 10`.
- Grade scale is exactly `("hard", "good", "easy")`; `"again"` is retired but must keep classifying in analytics forever.
- Run pytest with `./.venv/bin/python -m pytest`; run Django commands with `backend/venv/bin/python manage.py`.

---

### Task 1: Three-grade scale, with Hard resetting

Removes `again` from the grade scale and gives `hard` the reset-to-day-one behaviour it used to carry. Analytics keeps classifying historical `again` rows, so no data migration is needed.

**Files:**
- Modify: `backend/study_sessions/scheduling.py:18-20` (constants), `:56-70` (the AGAIN/HARD branches)
- Modify: `backend/analytics/insights.py:24-25`
- Test: `tests/test_spaced_repetition.py:32-45`, `:101`, `:120-125`, `:153-157`

**Interfaces:**
- Consumes: nothing.
- Produces: `scheduling.RESULT_VALUES == ("hard", "good", "easy")`, `scheduling.HARD == "hard"`, `scheduling.RETIRED_RESULTS == frozenset({"again"})`, `scheduling.CORRECT_RESULTS == frozenset({"good", "easy"})`. Task 3 and Task 5 import `scheduling.HARD`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_spaced_repetition.py`, replace the `# ---- again: the card was forgotten ----` block (lines 32-45) with:

```python
# ---- hard: the card was forgotten or barely recalled ------------------------

def test_hard_restarts_the_card():
    s = _step("hard", interval=21, ease_factor=2.5, repetitions=5)
    assert s.interval == 1
    assert s.repetitions == 0


def test_hard_makes_the_card_harder():
    assert _step("hard", ease_factor=2.5).ease_factor == pytest.approx(2.3)


def test_again_is_no_longer_a_grade():
    assert "again" not in sm2.RESULT_VALUES
    with pytest.raises(ValueError):
        sm2.next_schedule("again", interval=1, ease_factor=2.5, repetitions=0)
```

Replace the mirror test (lines 153-157) with:

```python
def test_insights_and_scheduling_agree_on_what_counts_as_correct():
    assert ins.CORRECT_RESULTS == sm2.CORRECT_RESULTS
    # Every grade the app can record today must be classified by insights.
    assert set(sm2.RESULT_VALUES) <= (ins.CORRECT_RESULTS | ins.INCORRECT_RESULTS)
    # Retired grades stay classified so historical rows keep counting.
    assert sm2.RETIRED_RESULTS <= ins.INCORRECT_RESULTS
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_spaced_repetition.py -v`
Expected: FAIL — `test_again_is_no_longer_a_grade` fails because `"again"` is still in `RESULT_VALUES`, and `test_hard_restarts_the_card` fails because hard returns interval 22, not 1.

- [ ] **Step 3: Update the grade constants**

In `backend/study_sessions/scheduling.py`, replace lines 18-20:

```python
# Grades, easiest-to-recall last. These mirror CardReview.RESULT_CHOICES.
HARD, GOOD, EASY = "hard", "good", "easy"
RESULT_VALUES = (HARD, GOOD, EASY)

#: Grades that count as a successful recall when reporting accuracy. This module
#: is the source of truth; analytics.insights mirrors it (a test holds them
#: level) because it is loaded standalone and cannot import from here.
CORRECT_RESULTS = frozenset({GOOD, EASY})

#: Grades no longer offered, but still present on rows recorded before they were
#: retired. `next_schedule` rejects them; analytics must still classify them, or
#: a learner's history would silently lose its failures.
RETIRED_RESULTS = frozenset({"again"})
```

- [ ] **Step 4: Give Hard the reset behaviour**

In the same file, delete the `if result == AGAIN:` branch and replace the `if result == HARD:` branch with:

```python
    if result == HARD:
        # Forgotten, or recalled only with effort: back to square one, and the
        # card earns a harder rating. This is now the only grade that resets a
        # card, so it is what stops material the learner cannot recall from
        # drifting steadily further away.
        return Schedule(1, max(MIN_EASE_FACTOR, ease_factor - 0.2), 0)
```

- [ ] **Step 5: Keep historical grades classified in analytics**

In `backend/analytics/insights.py`, replace lines 24-25:

```python
CORRECT_RESULTS = frozenset({"good", "easy"})
# "again" was retired from the grade scale on 2026-07-25. Rows recorded before
# then still exist, and must keep counting as failures — dropping it here would
# quietly rewrite every affected learner's past accuracy.
INCORRECT_RESULTS = frozenset({"again", "hard"})
```

- [ ] **Step 6: Fix the remaining parametrised references**

In `tests/test_spaced_repetition.py` line 101, change `@pytest.mark.parametrize("result", ["again", "hard"])` to:

```python
@pytest.mark.parametrize("result", ["hard"])
```

At line 122, change `sm2.next_schedule("again", ...)` to `sm2.next_schedule("hard", ...)`.

- [ ] **Step 7: Run the whole suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: PASS, 200+ passed.

- [ ] **Step 8: Commit**

```bash
git add backend/study_sessions/scheduling.py backend/analytics/insights.py tests/test_spaced_repetition.py
git commit -m "feat(study): drop the Again grade and let Hard reset the card"
```

---

### Task 2: Model fields, indexes, and migrations

Adds the lineage and flag fields the regeneration flow needs, plus the seed marker that lets a variant inherit a schedule without polluting accuracy.

**Files:**
- Modify: `backend/flashcards/models.py:5-27`
- Modify: `backend/study_sessions/models.py` (the `CardReview` class)
- Create: `backend/flashcards/migrations/0002_flashcard_variants.py` (generated)
- Create: `backend/study_sessions/migrations/0002_cardreview_is_seed.py` (generated)

**Interfaces:**
- Consumes: nothing.
- Produces: `Flashcard.origin`, `Flashcard.archived`, `Flashcard.needs_regeneration`, `Flashcard.generation`; `CardReview.is_seed` and `CardReview.objects.grades()`. Tasks 3, 5 and 6 rely on these.

- [ ] **Step 1: Add the Flashcard fields and indexes**

In `backend/flashcards/models.py`, add these fields after `incorrect_count`:

```python
    # Regeneration lineage. A card the learner keeps failing is replaced by a
    # freshly generated question on the same concept; the original is archived
    # rather than deleted so its review history survives.
    origin = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='variants',
        help_text='The card this one was regenerated from.',
    )
    archived = models.BooleanField(
        default=False,
        help_text='Retired by regeneration; excluded from every study queue.',
    )
    needs_regeneration = models.BooleanField(
        default=False,
        help_text='Graded hard; replace with a new question when next due.',
    )
    generation = models.PositiveIntegerField(
        default=0,
        help_text='How many times this concept has been regenerated.',
    )
```

Replace the `indexes` list in `Meta`:

```python
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['topic', '-created_at']),
            # Study queues read active cards only, and the due-fetch looks for
            # flagged ones. Both run on every study page load.
            models.Index(fields=['user', 'archived']),
            models.Index(fields=['user', 'needs_regeneration', 'archived']),
        ]
```

- [ ] **Step 2: Add the CardReview seed marker and a queryset that hides it**

In `backend/study_sessions/models.py`, add above `class CardReview`:

```python
class CardReviewQuerySet(models.QuerySet):
    def grades(self):
        """Only rows recording an actual recall.

        Seed rows carry a schedule to a regenerated card and represent no
        answer, so counting them would inflate review totals and dilute
        accuracy. Scheduling reads the unfiltered manager on purpose — a seed
        row is exactly what tells a variant when it is next due.
        """
        return self.filter(is_seed=False)
```

Inside `CardReview`, add the field and manager:

```python
    is_seed = models.BooleanField(
        default=False,
        help_text='Carries a schedule to a regenerated card; not a real recall.',
    )

    objects = CardReviewQuerySet.as_manager()
```

- [ ] **Step 3: Generate the migrations**

```bash
cd backend && ./venv/bin/python manage.py makemigrations flashcards study_sessions
```

Expected: two migration files created, listing `AddField` for `origin`, `archived`, `needs_regeneration`, `generation`, `is_seed`, plus `AddIndex` entries. All new fields have defaults, so no `RunPython` data migration appears — that is required; if Django prompts for a default, stop and give the field one in the model instead.

- [ ] **Step 4: Apply and verify reversibility**

```bash
cd backend && ./venv/bin/python manage.py migrate
./venv/bin/python manage.py migrate flashcards 0001 && ./venv/bin/python manage.py migrate flashcards
```

Expected: applies cleanly, rolls back to `0001` without error, then re-applies. A migration that cannot roll back is a defect — fix it before continuing.

- [ ] **Step 5: Commit**

```bash
git add backend/flashcards/models.py backend/study_sessions/models.py backend/flashcards/migrations backend/study_sessions/migrations
git commit -m "feat(flashcards): add regeneration lineage fields and schedule seeds"
```

---

### Task 3: Flag a card when it is graded Hard

Grading must stay instant, so this only sets a flag — no model call happens here.

**Files:**
- Modify: `backend/study_sessions/models.py` (`CardReview.record`)
- Modify: `backend/study_sessions/views.py:236-247` (the `stats` action)

**Interfaces:**
- Consumes: `scheduling.HARD` (Task 1), `Flashcard.needs_regeneration` and `CardReview.objects.grades()` (Task 2).
- Produces: a card graded `hard` has `needs_regeneration=True`. Task 5 consumes that flag.

- [ ] **Step 1: Set the flag inside `record`**

In `backend/study_sessions/models.py`, in `CardReview.record`, after `review.calculate_next_review()` and before the streak block:

```python
        # A failed card comes back as a different question on the same concept,
        # but generating one costs a model call, so only mark it here. The
        # due-fetch does the work, and only for cards actually returned to.
        if result == scheduling.HARD and not flashcard.needs_regeneration:
            flashcard.needs_regeneration = True
            flashcard.save(update_fields=['needs_regeneration'])
```

- [ ] **Step 2: Keep seed rows out of the review statistics**

In `backend/study_sessions/views.py`, in the `stats` action, change the three queries to use `.grades()`:

```python
        total_reviews = CardReview.objects.grades().filter(user=user).count()
        reviews_this_week = CardReview.objects.grades().filter(
            user=user,
            review_date__date__gte=week_ago
        ).count()
        accuracy_this_week = CardReview.objects.grades().filter(
            user=user,
            review_date__date__gte=week_ago,
            result__in=['good', 'easy']
        ).count()
```

- [ ] **Step 3: Verify nothing regressed**

Run: `./.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/study_sessions/models.py backend/study_sessions/views.py
git commit -m "feat(study): flag hard-graded cards for regeneration"
```

---

### Task 4: The variant generator

A Django-free module: it receives the card's text, an optional source excerpt, and a provider object, and returns a new question on the same concept.

**Files:**
- Create: `backend/flashcards/services/__init__.py`
- Create: `backend/flashcards/services/variant_generator.py`
- Create: `tests/test_variant_generator.py`

**Interfaces:**
- Consumes: `notebooks.services.dedupe.normalize_question` (existing).
- Produces:
  - `build_variant_prompt(question: str, answer: str, excerpt: str) -> str`
  - `reformat_fallback(question: str, answer: str) -> dict | None`
  - `generate_variant(question: str, answer: str, provider, excerpt: str = "") -> dict | None` returning `{"question": str, "answer": str, "difficulty": str}` or `None`.
  Task 5 calls `generate_variant`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_variant_generator.py`, following the repo's standalone-module loading pattern:

```python
"""The variant generator: a failed card becomes a different question."""
import importlib.util
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
_MODULE_PATH = _BACKEND_DIR / "flashcards" / "services" / "variant_generator.py"


def _load():
    # The module under test imports `notebooks.services.dedupe`, which resolves
    # the way it does under Django: with backend/ on the path. Adding it here
    # keeps the module loadable standalone, without importing Django itself.
    if str(_BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(_BACKEND_DIR))
    spec = importlib.util.spec_from_file_location("variant_generator_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vg = _load()


class FakeProvider:
    """Returns queued payloads; raises if it runs out."""

    def __init__(self, *payloads):
        self._payloads = list(payloads)
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        if not self._payloads:
            raise RuntimeError("provider exhausted")
        payload = self._payloads.pop(0)
        if isinstance(payload, Exception):
            raise payload
        return payload


def _card():
    return "What is photosynthesis?", "Conversion of light into chemical energy"


def test_returns_a_question_different_from_the_original():
    provider = FakeProvider({"question": "Which gas do plants release during photosynthesis?",
                             "answer": "Oxygen"})
    result = vg.generate_variant(*_card(), provider=provider)
    assert result["question"] == "Which gas do plants release during photosynthesis?"
    assert result["answer"] == "Oxygen"
    assert result["difficulty"] in ("easy", "medium", "hard")


def test_excerpt_is_included_in_the_prompt():
    provider = FakeProvider({"question": "Q?", "answer": "A"})
    vg.generate_variant(*_card(), provider=provider, excerpt="Chlorophyll absorbs light.")
    assert "Chlorophyll absorbs light." in provider.prompts[0]


def test_a_variant_matching_the_original_is_retried_then_falls_back():
    original_q, original_a = _card()
    # First reply repeats the original question; the retry gives a real variant.
    provider = FakeProvider({"question": original_q, "answer": original_a},
                            {"question": "Photosynthesis stores energy in what form?",
                             "answer": "Chemical bonds"})
    result = vg.generate_variant(original_q, original_a, provider=provider)
    assert result["question"] == "Photosynthesis stores energy in what form?"
    assert len(provider.prompts) == 2


def test_provider_failure_falls_back_to_a_reformat():
    provider = FakeProvider(RuntimeError("ollama down"), RuntimeError("still down"))
    result = vg.generate_variant(*_card(), provider=provider)
    assert result is not None
    assert result["question"] != _card()[0]


def test_returns_none_when_nothing_usable_can_be_produced():
    provider = FakeProvider(RuntimeError("down"), RuntimeError("down"))
    # Too short to reformat into anything meaningful.
    assert vg.generate_variant("Q?", "", provider=provider) is None


def test_reformat_fallback_turns_a_definition_into_a_cloze():
    result = vg.reformat_fallback("What is photosynthesis?",
                                  "Conversion of light into chemical energy")
    assert result is not None
    assert "______" in result["question"]
    assert result["answer"] == "Photosynthesis" or result["answer"]


def test_malformed_payload_is_treated_as_a_failure():
    provider = FakeProvider({"nonsense": True}, {"nonsense": True})
    result = vg.generate_variant(*_card(), provider=provider)
    # Falls back rather than raising.
    assert result is None or result["question"] != _card()[0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_variant_generator.py -v`
Expected: FAIL — `FileNotFoundError` / `spec_from_file_location` returns None, because `variant_generator.py` does not exist yet.

- [ ] **Step 3: Create the services package**

```bash
touch backend/flashcards/services/__init__.py
```

Do **not** create `backend/__init__.py`. Django puts `backend/` itself on the path (`BASE_DIR`) and refers to its apps as top-level modules (`flashcards`, `notebooks`); making `backend` a package as well would give every app two importable names and two module identities.

- [ ] **Step 4: Write the generator**

Create `backend/flashcards/services/variant_generator.py`:

```python
"""Regenerate a failed flashcard as a different question on the same concept.

A learner who keeps failing a card ends up memorising its wording rather than
the material, so re-study stops testing anything. This produces a fresh question
about the same concept, grounded in the source excerpt so the model cannot drift
onto material the learner never read.

No Django imports: the caller passes the card's text and its provider, so the
prompt building, parsing and fallback stay unit-testable in isolation.
"""
from __future__ import annotations

import re

BLANK = "______"
_WORD = re.compile(r"\w+")

# Below this many characters, a card carries too little to reformat into a
# meaningful question, so failing outright beats emitting nonsense.
MIN_REFORMAT_CHARS = 12


def _normalize(text: str | None) -> str:
    """Fold a question the way dedupe does, so 'the same' means the same here."""
    from notebooks.services.dedupe import normalize_question
    return normalize_question(text)


def build_variant_prompt(question: str, answer: str, excerpt: str) -> str:
    """Ask for one new question on the concept the failed card tests."""
    grounding = (
        f"\nGround the question in this source excerpt, and make it answerable "
        f"from the excerpt alone:\n{excerpt[:2000]}\n" if excerpt.strip() else ""
    )
    return f"""A student keeps failing this flashcard, so they have memorised its
wording rather than the material.

Existing question: {question}
Existing answer: {answer}

Write ONE different flashcard that tests the same underlying concept from
another angle. Use different wording, and prefer a different facet of the
concept. Do not restate the existing question.
{grounding}
Return ONLY valid JSON:
{{"question": "...", "answer": "...", "difficulty": "easy|medium|hard"}}
"""


def _clean(payload: dict) -> dict | None:
    """Validate a model payload into a card, or None if it is unusable."""
    if not isinstance(payload, dict):
        return None
    question = str(payload.get("question") or "").strip()
    answer = str(payload.get("answer") or "").strip()
    if not question or not answer:
        return None
    difficulty = str(payload.get("difficulty") or "medium").strip().lower()
    if difficulty not in ("easy", "medium", "hard"):
        difficulty = "medium"
    return {"question": question, "answer": answer, "difficulty": difficulty}


def reformat_fallback(question: str, answer: str) -> dict | None:
    """Turn the card around without a model: ask for the term, given its meaning.

    Deliberately deterministic. It cannot invent a new angle, but it always
    changes what the learner is asked to produce, which is enough to stop a
    memorised string from scoring.
    """
    question, answer = (question or "").strip(), (answer or "").strip()
    if len(answer) < MIN_REFORMAT_CHARS:
        return None
    subject = _WORD.findall(question)
    term = subject[-1] if subject else ""
    if not term:
        return None
    return {
        "question": f"{answer.rstrip('.')} — which term does this describe? ({BLANK})",
        "answer": term.capitalize(),
        "difficulty": "medium",
    }


def generate_variant(question: str, answer: str, provider,
                     excerpt: str = "") -> dict | None:
    """A new question on the same concept, or None to keep the original.

    Tries the provider twice — a model that echoes the original once will often
    comply when told plainly — then falls back to a deterministic reformat.
    Returning None is a valid outcome: the card simply stays as it is and is
    retried next time, which is why nothing here raises.
    """
    original_key = _normalize(question)
    prompt = build_variant_prompt(question, answer, excerpt)

    for attempt in range(2):
        text = prompt if attempt == 0 else (
            prompt + "\nYour previous answer repeated the existing question. "
                     "Ask about a different aspect of the concept."
        )
        try:
            card = _clean(provider.generate_json(text))
        except Exception:
            card = None
        if card and _normalize(card["question"]) != original_key:
            return card

    return reformat_fallback(question, answer)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_variant_generator.py -v`
Expected: PASS, 7 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/__init__.py backend/flashcards/services tests/test_variant_generator.py
git commit -m "feat(flashcards): generate a fresh question for a failed card"
```

---

### Task 5: Replace flagged cards when due cards are fetched

The lazy half: flagged cards that are actually due get regenerated, the original is archived, and the variant inherits its schedule.

**Files:**
- Create: `backend/flashcards/services/regeneration.py`
- Modify: `backend/study_sessions/views.py:200-218` (`due_today`)
- Test: `tests/test_regeneration_policy.py`

**Interfaces:**
- Consumes: `generate_variant` (Task 4); `Flashcard.needs_regeneration` / `archived` / `origin` / `generation`, `CardReview.is_seed` (Task 2).
- Produces: `select_for_regeneration(cards, limit) -> list[dict]` and `replace_card(card, variant, provider_name) -> Flashcard`.

- [ ] **Step 1: Write the failing test for the selection policy**

Create `tests/test_regeneration_policy.py`:

```python
"""Which flagged cards get regenerated on a given due-fetch."""
import importlib.util
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "flashcards" / "services" / "regeneration.py")


def _load():
    spec = importlib.util.spec_from_file_location("regeneration_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


select_for_regeneration = _load().select_for_regeneration


def _card(card_id, *, flagged, status="due"):
    return {"id": card_id, "needs_regeneration": flagged, "status": status}


def test_only_flagged_due_cards_are_selected():
    cards = [
        _card(1, flagged=True),
        _card(2, flagged=False),
        _card(3, flagged=True, status="new"),
    ]
    assert [c["id"] for c in select_for_regeneration(cards, limit=5)] == [1]


def test_selection_is_capped_so_one_fetch_cannot_stall():
    cards = [_card(i, flagged=True) for i in range(1, 11)]
    assert len(select_for_regeneration(cards, limit=3)) == 3


def test_nothing_flagged_means_no_work():
    assert select_for_regeneration([_card(1, flagged=False)], limit=5) == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_regeneration_policy.py -v`
Expected: FAIL with `ModuleNotFoundError` / `ImportError`.

- [ ] **Step 3: Write the regeneration module**

Create `backend/flashcards/services/regeneration.py`:

```python
"""Replacing a failed flashcard with a fresh question on the same concept.

Split in two. `select_for_regeneration` is a pure policy — which flagged cards
are worth the model calls on this fetch — and is unit-tested without a database.
`replace_card` performs the swap and needs Django, so it is kept deliberately
small.
"""
from __future__ import annotations

#: Model calls are seconds each, and a due-fetch blocks the study page, so a
#: backlog is worked through a few cards at a time rather than all at once.
MAX_REGENERATIONS_PER_FETCH = 3


def select_for_regeneration(cards: list[dict], limit: int) -> list[dict]:
    """The flagged, currently-due cards to regenerate on this fetch.

    New cards are excluded: a card never studied has no memorised wording to
    escape, so spending a model call on it buys nothing.
    """
    flagged = [c for c in cards
               if c.get("needs_regeneration") and c.get("status") == "due"]
    return flagged[:limit]


def replace_card(card, variant: dict, generation_source: str = ""):
    """Archive `card` and return its replacement, carrying the schedule over.

    The variant must inherit the original's next-review date, or a card the
    learner just failed would silently leave the queue. The seed review is
    marked `is_seed` so it schedules without counting as a recall.
    """
    from django.utils import timezone
    from flashcards.models import Flashcard
    from study_sessions.models import CardReview

    replacement = Flashcard.objects.create(
        user=card.user,
        topic=card.topic,
        question=variant["question"],
        answer=variant["answer"],
        difficulty=variant.get("difficulty", "medium"),
        tags=card.tags,
        is_public=False,
        origin=card,
        generation=card.generation + 1,
    )

    previous = CardReview.objects.filter(user=card.user, flashcard=card).first()
    CardReview.objects.create(
        user=card.user,
        flashcard=replacement,
        result="seed",
        is_seed=True,
        interval=previous.interval if previous else 1,
        ease_factor=previous.ease_factor if previous else 2.5,
        repetitions=previous.repetitions if previous else 0,
        next_review_date=(previous.next_review_date if previous
                          else timezone.localdate()),
    )

    card.archived = True
    card.needs_regeneration = False
    card.save(update_fields=['archived', 'needs_regeneration'])
    return replacement
```

Note the seed row stores `result="seed"`, which is deliberately outside
`RESULT_VALUES`: `insights.tally_reviews` already skips unknown grades, so
accuracy stays correct even if a future query forgets to call `.grades()`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_regeneration_policy.py -v`
Expected: PASS, 3 passed.

- [ ] **Step 5: Wire it into the due-cards fetch**

In `backend/study_sessions/views.py`, replace the body of `due_today` after the `schedule = ...` block:

```python
        cards = list(Flashcard.objects.filter(user=user, archived=False)
                     .values('id', 'question', 'answer', 'difficulty', 'tags',
                             'needs_regeneration'))
        ranked = scheduling.rank_due_cards(cards, schedule, timezone.localdate(),
                                           limit=limit)

        pending = select_for_regeneration(ranked, MAX_REGENERATIONS_PER_FETCH)
        if pending:
            ranked = _swap_in_variants(user, ranked, pending)

        return Response(ranked)
```

Add this helper above the class:

```python
def _swap_in_variants(user, ranked, pending):
    """Replace each flagged card in `ranked` with a freshly generated one.

    A failure here must never cost the learner their study session, so a card
    that cannot be regenerated is simply returned unchanged and retried on the
    next fetch.
    """
    from notebooks.services.ai_provider import get_ai_provider
    from notebooks.services.generate import SOURCE_TAG_PREFIX
    from flashcards.services.variant_generator import generate_variant
    from flashcards.services.regeneration import replace_card
    from notebooks.models import Source

    provider = get_ai_provider()
    replacements = {}
    for entry in pending:
        card = Flashcard.objects.filter(id=entry['id'], user=user).first()
        if card is None:
            continue
        excerpt = _source_excerpt(user, card.tags)
        try:
            variant = generate_variant(card.question, card.answer,
                                       provider=provider, excerpt=excerpt)
        except Exception:
            variant = None
        if not variant:
            continue
        new_card = replace_card(card, variant)
        replacements[entry['id']] = {
            'id': new_card.id, 'question': new_card.question,
            'answer': new_card.answer, 'difficulty': new_card.difficulty,
            'tags': new_card.tags, 'status': entry['status'],
            'overdue_days': entry['overdue_days'], 'regenerated': True,
        }

    return [replacements.get(c['id'], c) for c in ranked]


def _source_excerpt(user, tags, limit=4000):
    """The text the card was generated from, so a variant stays on topic."""
    from notebooks.models import Source
    from notebooks.services.generate import SOURCE_TAG_PREFIX

    if not tags or not tags.startswith(SOURCE_TAG_PREFIX):
        return ""
    raw = tags[len(SOURCE_TAG_PREFIX):]
    ids = [int(i) for i in raw.split(',') if i.strip().isdigit()]
    if not ids:
        return ""
    texts = Source.objects.filter(
        id__in=ids, notebook__user=user
    ).values_list('extracted_text', flat=True)
    return "\n\n".join(t for t in texts if t)[:limit]
```

Add the imports at the top of the file:

```python
from flashcards.services.regeneration import (
    MAX_REGENERATIONS_PER_FETCH, select_for_regeneration,
)
```

- [ ] **Step 6: Verify the whole suite still passes**

Run: `./.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Verify by hand against the running app**

```bash
cd backend && ./venv/bin/python manage.py check
```
Expected: no errors beyond the pre-existing `W042` warnings.

Then, with `pnpm dev:all` running and Ollama up: study a card, grade it **Hard**, reload the flashcards page, and confirm the card returns with a *different* question. Confirm in the Django admin that the original now has `archived=True` and the new card has `origin` set and `generation=1`.

- [ ] **Step 8: Commit**

```bash
git add backend/flashcards/services/regeneration.py backend/study_sessions/views.py tests/test_regeneration_policy.py
git commit -m "feat(flashcards): swap a failed card for a fresh question when it comes due"
```

---

### Task 6: Cap a document at ten active cards

Stops repeated generation from stacking cards without limit.

**Files:**
- Create: `backend/notebooks/services/deck_limits.py`
- Create: `tests/test_deck_limits.py`
- Modify: `backend/notebooks/services/generate.py:123-163` (`_save_flashcards_from_json`), `:166-171` (`generate_flashcards_for_sources`)

**Interfaces:**
- Consumes: `Flashcard.archived` (Task 2).
- Produces: `MAX_CARDS_PER_SOURCE = 10` and `room_for(existing_active: int, maximum: int = MAX_CARDS_PER_SOURCE) -> int`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_deck_limits.py`:

```python
"""How much room a document has left for new flashcards."""
import importlib.util
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "notebooks" / "services" / "deck_limits.py")


def _load():
    spec = importlib.util.spec_from_file_location("deck_limits_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load()
MAX_CARDS_PER_SOURCE = _mod.MAX_CARDS_PER_SOURCE
room_for = _mod.room_for


def test_an_empty_document_has_room_for_the_whole_cap():
    assert room_for(0) == MAX_CARDS_PER_SOURCE


def test_a_partly_filled_document_tops_up():
    assert room_for(6) == 4


def test_a_full_document_has_no_room():
    assert room_for(MAX_CARDS_PER_SOURCE) == 0


def test_room_never_goes_negative():
    # Documents generated before the cap existed can exceed it; they must not
    # produce a negative request that would read as "unlimited" downstream.
    assert room_for(25) == 0


def test_the_cap_is_ten():
    assert MAX_CARDS_PER_SOURCE == 10
```

- [ ] **Step 2: Run to verify failure**

Run: `./.venv/bin/python -m pytest tests/test_deck_limits.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write the module**

Create `backend/notebooks/services/deck_limits.py`:

```python
"""How many more flashcards a document may hold.

Generating appends, and dedupe only rejects questions the document already
asks, so without a ceiling a document generated from three times carries thirty
cards and the learner's queue fills with one subject. No Django imports, so the
arithmetic is unit-testable on its own.
"""
from __future__ import annotations

#: Active cards a single source selection may hold. Ten is a sitting's worth.
MAX_CARDS_PER_SOURCE = 10


def room_for(existing_active: int, maximum: int = MAX_CARDS_PER_SOURCE) -> int:
    """How many cards may still be added. Never negative.

    Counts active cards only: regeneration archives a card and adds its
    replacement, so a document that refreshes a failed card stays at its cap
    rather than creeping past it.
    """
    return max(0, maximum - existing_active)
```

- [ ] **Step 4: Run to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_deck_limits.py -v`
Expected: PASS, 5 passed.

- [ ] **Step 5: Enforce the ceiling when saving**

In `backend/notebooks/services/generate.py`, add to the imports:

```python
from .deck_limits import MAX_CARDS_PER_SOURCE, room_for
```

Change the signature and body of `_save_flashcards_from_json`. Replace lines 123-137 with:

```python
def _save_flashcards_from_json(
    data: dict, user, source_ids: list[int], count: int
) -> list[Flashcard]:
    items = data.get('flashcards') or []
    if not items:
        raise GeminiGenerationError('No flashcards were generated.')

    tag = combined_source_tag(source_ids)
    # Generating again appends, so without this the same fact reaches two cards
    # with two schedules and gets reviewed twice. Scoped to this exact source
    # selection — the set the caller asked to generate from.
    existing = list(
        Flashcard.objects.filter(user=user, tags=tag, archived=False)
        .values_list('question', flat=True)
    )
    # The hard ceiling lives here rather than at the request, because the
    # `max(3, ...)` clamp upstream would raise a one-slot top-up back to three.
    allowed = min(count, room_for(len(existing)))
    fresh = dedupe.new_flashcards(items[:count], existing)[:allowed]
```

- [ ] **Step 6: Ask for only what fits**

In `generate_flashcards_for_sources`, replace lines 169-171 with:

```python
    count = max(3, min(count, 20))
    source_ids = [s.id for s in sources]
    tag = combined_source_tag(source_ids)

    # A full document is a finished document, not an error: say so and stop
    # before spending a model call that could not be saved anyway.
    already = Flashcard.objects.filter(user=user, tags=tag, archived=False).count()
    if room_for(already) == 0:
        _mark(meta, 'none', reason=f'already at the {MAX_CARDS_PER_SOURCE}-card limit')
        return []
```

- [ ] **Step 7: Run the suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 8: Verify by hand**

With the app running, generate flashcards from one document three times. Expected: the document holds exactly ten cards, and the third press reports that it is already at the limit rather than erroring.

- [ ] **Step 9: Commit**

```bash
git add backend/notebooks/services/deck_limits.py backend/notebooks/services/generate.py tests/test_deck_limits.py
git commit -m "feat(flashcards): cap a document at ten active cards"
```

---

### Task 7: Frontend — three grades and a visible cap

**Files:**
- Modify: `app/dashboard/flashcards/page.tsx:33-38` (the `GRADES` array)
- Modify: `lib/api.ts:52` (the `ReviewGrade` type)
- Modify: `components/notebook-workspace.tsx` (the generate button label)

**Interfaces:**
- Consumes: the API's three-grade scale (Task 1) and the cap (Task 6).
- Produces: no exports other tasks depend on.

- [ ] **Step 1: Narrow the grade type**

In `lib/api.ts`, change the `ReviewGrade` type:

```typescript
/** How well you recalled a card, worst first. Drives the SM-2 schedule. */
export type ReviewGrade = 'hard' | 'good' | 'easy'
```

- [ ] **Step 2: Remove the Again button**

In `app/dashboard/flashcards/page.tsx`, replace the `GRADES` array:

```typescript
const GRADES: { value: ReviewGrade; label: string; hint: string; className: string }[] = [
  { value: 'hard', label: 'Hard', hint: 'Forgot', className: 'border-red-300 bg-red-50 text-red-900 hover:bg-red-100' },
  { value: 'good', label: 'Good', hint: 'Recalled', className: 'border-sky-300 bg-sky-50 text-sky-900 hover:bg-sky-100' },
  { value: 'easy', label: 'Easy', hint: 'Instantly', className: 'border-emerald-300 bg-emerald-50 text-emerald-900 hover:bg-emerald-100' },
]
```

Hard keeps the red styling because it is now the grade that means "I did not know this"; the keyboard shortcuts renumber to 1-3 automatically because they are derived from the array index.

- [ ] **Step 3: Show the cap on the generate button**

In `components/notebook-workspace.tsx`, find the flashcard generate button label and show the count against the cap, disabling it when full. The existing `material_counts` fetch already supplies `flashcards`:

```typescript
const cardCount = materialCounts?.flashcards ?? 0
const deckFull = cardCount >= 10
```

Use `deckFull` for the button's `disabled` prop and render the label as:

```typescript
{generating === 'flashcards' ? 'Generating…' : deckFull ? 'Flashcards full (10/10)' : `Generate flashcards (${cardCount}/10)`}
```

- [ ] **Step 4: Typecheck**

Run: `npx tsc --noEmit`
Expected: exit 0, no errors. Any error about `'again'` no longer being assignable points at a spot still sending the retired grade — fix it rather than widening the type back.

- [ ] **Step 5: Verify by hand**

With the app running: the study page shows three buttons, keys 1-3 grade a card, and the notebook page shows `Generate flashcards (n/10)`, disabled at ten.

- [ ] **Step 6: Commit**

```bash
git add app/dashboard/flashcards/page.tsx lib/api.ts components/notebook-workspace.tsx
git commit -m "feat(flashcards): three grades, and show the ten-card limit"
```

---

## Self-Review

**Spec coverage.** Every section of the spec maps to a task: three-grade scale and the historical-`again` handling → Task 1; the four `Flashcard` fields, `is_seed`, and indexes → Task 2; the *Hard* flag → Task 3; the variant generator with its dedupe retry and reformat fallback → Task 4; lazy replacement, archiving, and schedule seeding → Task 5; the ten-card cap including the `max(3, ...)` clamp interaction → Task 6; the frontend grade removal and cap indicator → Task 7.

**Two long-term defects found and fixed while planning:**
1. The existing mirror test asserts `CORRECT | INCORRECT == set(RESULT_VALUES)`, which would fail once `again` left the scale while remaining in `INCORRECT_RESULTS` for historical rows. Task 1 changes it to a subset assertion plus an explicit `RETIRED_RESULTS` check, so retired grades keep counting.
2. `stats` counted every `CardReview` row, so schedule seeds would have inflated "reviews this week" and diluted accuracy. Task 3 routes those queries through `CardReview.objects.grades()`, and seeds additionally use `result="seed"` so `tally_reviews` skips them even if a future query forgets.

**Type consistency.** `generate_variant(question, answer, provider, excerpt)` returns `{"question", "answer", "difficulty"}` in Task 4 and is consumed with exactly those keys in Task 5. `room_for` and `MAX_CARDS_PER_SOURCE` keep the same names across Tasks 6 and 7. `select_for_regeneration(cards, limit)` matches its call site.

**Known constraint.** Tests are pure unit tests because the project's Postgres role cannot create a test database. If that is granted later (`ALTER ROLE <user> CREATEDB;`), the Django-level flows in Tasks 3 and 5 become directly testable; until then Step 7 of Task 5 and Step 8 of Task 6 are manual verification against the running app.
