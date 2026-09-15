# Source Links as Relations — Design

**Date:** 2026-09-15
**Status:** Implemented 2026-09-15
**Author:** pairing session

## Problem

Every flashcard and quiz is generated from one or more of a notebook's
sources, and every later feature — the per-source study view, the mock-test
question pool, regeneration that retires the old deck, per-notebook mastery on
Analytics — needs to know which sources an item came from. That relationship
is currently stored as text:

- `Flashcard.tags` holds a bare `source:1,3`.
- `Quiz` has no field for it at all, so ` [source:1,3]` is appended to the
  end of `description` and parsed back out with a regex.

The consequences are already visible in the code, not hypothetical:

1. **Substring traps.** `source:1` is a prefix of `source:13`. Three places
   carry comments explaining why their match is "a prefilter, not the real
   check" ([quizzes/views.py](../../../backend/quizzes/views.py) `_source_filter`),
   or why brackets are needed to avoid the trap the frontend matcher falls into
   ([notebooks/views.py](../../../backend/notebooks/views.py) existing-count).
2. **Orphans.** Deleting a source leaves its id inside every tag that named it.
   Nothing removes it; analytics silently skips it.
3. **Fragility.** Editing a quiz's description — a plain text field the API
   accepts writes to — can destroy the link.
4. **No indexing.** Every lookup by source is a `LIKE '%source:3%'` scan or a
   full Python-side parse of the user's whole collection.

Nine backend files (~40 sites) and two frontend pages parse or build the tag.
The `tags` column exists for no other reason: no UI writes free-form tags.

## Goals

- Store the item → source relationship as a many-to-many relation on
  `Flashcard` and `Quiz`, enforced by the database.
- Remove every tag parser and builder, backend and frontend.
- Preserve existing behaviour exactly where it was intended, and fix it where
  the intent was clear but the string got in the way (the substring trap).
- Migrate the existing rows losslessly, reversibly.

## Non-goals

- Archiving or deleting cards when their last source is deleted (see
  "Deleted sources" below — deliberately left as-is).
- Adding a `notebook` FK to `Quiz`. Its notebook is reachable through its
  sources; nothing today needs it directly.
- Free-form user tags. `tags` goes away; a tagging feature, if ever wanted,
  would be designed on its own terms.
- Any change to what is generated, or to the SM-2 schedule.

## Design

### Schema

```python
# flashcards/models.py
sources = models.ManyToManyField(
    'notebooks.Source', related_name='flashcards', blank=True,
    help_text='The documents this card was generated from.')
# `tags` removed.

# quizzes/models.py
sources = models.ManyToManyField(
    'notebooks.Source', related_name='quizzes', blank=True,
    help_text='The documents this quiz was generated from.')
# `description` is a description again; nothing is appended to it.
```

Both `blank=True`: a card created by hand through the API, or a quiz authored
directly, legitimately has no sources.

### Two semantics, stated once

The string encoded two different questions, and the answers must not drift
apart when the encoding changes.

**"What is the deck for this selection?"** — used by regeneration
(`_replace_deck` retires the previous deck) and by the notebook workspace's
existing-count. A deck is the set of cards generated from *exactly* this
selection. Query: cards having each selected source **and**
`Count('sources') == len(selection)`. Same for the "existing quiz" lookup.

**"Show me what relates to these sources"** — the `/flashcards?source=1,3`
and `/quizzes?source=…` views, and the mock-test pool. Old behaviour was
`tags.includes("source:1,3")` — a substring test whose evident intent was
"cards touching this selection". New rule: the item's sources **contain all**
of the selected sources (superset). For the pool, which already used
"any overlap" semantics after parsing, keep any-overlap:
`filter(quiz__sources__in=ids).distinct()`.

### Migration

Two migrations per app, so that every commit between them runs against a
database in either state:

1. **Add + copy** (first commit of the work): `AddField` the M2M, then
   `RunPython` forward parses the old tag (`tags` on flashcards; the
   `[source:…]` suffix on quiz descriptions), keeps only ids that exist in
   `notebooks.Source`, and writes the through rows. The old columns are left
   untouched, so code that still reads them keeps working.
2. **Remove + strip** (last commit): `RemoveField tags` on flashcards;
   `RunPython` on quizzes strips the ` [source:…]` suffix from `description`.

Each `RunPython` has a reverse that rebuilds the tag from the M2M (sorted
ids, comma-joined; quizzes re-append ` [source:…]` only if absent), so
`migrate <app> <previous>` restores the pre-change rows for every item whose
sources still exist. Ids that pointed at deleted sources are dropped on the
way forward and cannot be restored — they are the orphans this change exists
to stop carrying.

The dev database has 40 flashcards and 15 quizzes, all tagged; measured before
writing the plan, 20 flashcard links and 5 quiz links resolve to a live source,
and 20 + 11 ids point at sources that no longer exist. The forward migration
prints nothing; verification is a query after the fact (see Testing).

### Backend changes

| File | Change |
|---|---|
| `notebooks/services/generate.py` | Flashcards: `_replace_deck(cards, user, source_ids, notebook)` assigns `sources` and `notebook` to the new cards and retires the old deck by set-equality, all in its existing `transaction.atomic()` — it is already the one step every provider path shares, which is why `notebook` is assigned there and not at each creation site. Quizzes: `quiz.sources.set(source_ids)` right after `Quiz.objects.create`. Delete `combined_source_tag`, `SOURCE_TAG_PREFIX`, `tag_note`. |
| `notebooks/services/fallback.py`, `ml/adapter.py` | Drop the `tags=` kwarg and the `tag` parameter; flashcard paths rely on `_replace_deck` for sources, the ML quiz path calls `quiz.sources.set(...)` after create. |
| `notebooks/views.py` existing-count | Set-equality queries for both the card count and the latest quiz id. |
| `quizzes/views.py` | `_question_pool`: `Question.objects.filter(quiz__user=user, quiz__sources__in=ids).values('id', 'quiz__sources')`, grouped by question id. `_source_accuracy`: same shape over `Answer`. Delete `_source_filter` and its docstring. |
| `study_sessions/views.py` `_source_excerpt` | Signature becomes `(user, source_ids)`; caller passes `list(card.sources.values_list('id', flat=True))`. |
| `analytics/insights.py` | `flashcard_events(cards)` reads `card["source_ids"]`; `quiz_events(questions, answers)` reads `question["source_ids"]`. Delete `parse_source_ids`, `_SOURCE_TAG_RE`, `SOURCE_TAG_PREFIX`. |
| `analytics/views.py` | Supply `source_ids` per card and per question. Cards: one query over the through table grouped by card id. Questions: `values('id', 'quiz__sources')` grouped by question id. Both are two queries total, not N+1. |
| `flashcards/serializers.py`, `quizzes/serializers.py` | Add `source_ids = PrimaryKeyRelatedField(source='sources', many=True, read_only=True)`. Remove `tags` from `fields`; remove `'tags'` from `search_fields` in `flashcards/views.py`. |
| `flashcards/models.py` | Update the comment on `notebook` that references the old tag. |

`source_ids` is read-only on the API. Sources are assigned by generation, not
by clients; nothing today edits a card's provenance and exposing a writable
list would let a client claim a card belongs to a document it never saw.

### Frontend changes

- `lib/source-utils.ts`: delete `buildSourceTag`, `flashcardMatchesSourceTag`,
  `quizMatchesSourceTag`. Add
  `hasAllSources(itemSourceIds: number[], selected: number[]): boolean`
  (`selected.every(id => itemSourceIds.includes(id))`; empty `selected`
  → `false`, matching the old guards). `parseSourceIdsParam` and
  `formatSourceIdsForQuery` stay — the URL still carries `?source=1,3`.
- `app/dashboard/flashcards/page.tsx`: type `tags?: string | null` →
  `source_ids: number[]`; both filters use `hasAllSources`.
- `app/dashboard/quizzes/page.tsx`: same, over `q.source_ids` instead of
  `q.description`.
- `components/notebook-workspace.tsx`: one comment names
  `flashcardMatchesSourceTag`; reword.

### Deleted sources

Removing a source deletes its through rows. A card generated from `[1, 3]`
becomes a card of `[3]`; one generated from `[1]` alone becomes a card of
`[]`. Such a card still appears in the unfiltered study queue and in "all
cards", and drops out of per-source views and per-notebook mastery. That is
strictly better than today (a dead id kept forever) and is the natural
meaning of the relation. Whether a source-less card should be archived is a
product decision the study loop has not asked for; it is not made here.

### Error handling

- New cards get their sources in the same `transaction.atomic()` that retires
  the old deck. A crash before that block leaves fresh cards with no sources
  and the old deck still live — the same exposure the existing `notebook`
  assignment already accepts, and one a re-run of generation repairs. A crash
  inside the block rolls back everything.
- The forward migration skips ids that no longer resolve to a `Source`
  rather than failing; a tag that mentioned a deleted document is exactly the
  orphan this change exists to stop carrying.

## Testing

- **Pure (`tests/test_analytics_insights.py`)**: `flashcard_events` and
  `quiz_events` tests pass `source_ids` instead of `tags` /
  `quiz_description`. The three `parse_source_ids` tests are removed with the
  function. All `per_source_mastery` / `per_notebook_mastery` tests are
  unaffected — they already build events with `source_ids`.
- **Migration, on the dev database**: after the add + copy migrations,
  `Flashcard.sources.through` has 20 rows and `Quiz.sources.through` has 5
  (the live-source links measured above); after the remove + strip
  migrations, no `Quiz.description` contains `[source:`. Rolling back to
  `flashcards 0005` / `quizzes 0004` and forward again leaves every item
  whose ids resolved unchanged; items that only carried orphan ids come back
  with no tag, which is the expected loss.
- **Deck retirement (`_replace_deck`)**: exercised directly in a shell
  transaction — two cards handed to `_replace_deck` for selection `[9]`, then
  two more for the same selection: the first two are archived, the second two
  live, and cards of selection `[9, 11]` untouched.
- **ORM semantics, by request (APIClient, rolled back)**: generate → the
  existing-count endpoint reports the deck; generate again → the previous deck
  is archived and the count is unchanged; a card of `[1, 3]` is returned for
  `?source=1` and for `?source=1,3`, a card of `[1]` is not returned for
  `?source=1,3`.
- **Frontend**: `tsc --noEmit` clean; manual pass through notebook → generate
  from two sources → `/flashcards?source=…` → Analytics "By notebook".

## Out of scope, noted for later

- `Flashcard.notebook` and `Flashcard.sources` can disagree in principle
  (a card whose sources belong to a different notebook). Generation always
  sets both from the same request, so nothing produces that today; a
  constraint would need a database trigger or a `clean()` nobody calls.
