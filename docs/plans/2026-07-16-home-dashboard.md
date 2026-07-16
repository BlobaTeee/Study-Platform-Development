# Today Home Dashboard Implementation Plan

**Goal:** A `/dashboard` "Today" home page that surfaces existing data (due-card count, weekly stats, recent notebooks, weakest documents) and a live study streak, so the app opens onto what to do now instead of a bare list.

**Architecture:** The page is presentational over endpoints that already exist; only the streak needs a backend change. The streak's day-math moves into the pure `study_sessions/scheduling.py` module (mirroring `next_schedule`) so it is unit-testable, the model delegates to it, and `CardReview.record` calls it on every review so grading a card advances the streak.

**Tech Stack:** Django 5.2 / DRF (backend), Next.js 16 / React 19 / TypeScript / Tailwind 4 / SWR (frontend), pytest (backend tests). No JS test runner exists in this repo; frontend correctness is carried by `tsc` and the design system, so frontend helpers are kept trivial and pure logic lives in the tested backend module.

## Global Constraints

- Day boundaries use `timezone.localdate()`, never `timezone.now().date()` — the latter returns the UTC date regardless of `TIME_ZONE` and would misplace "consecutive day".
- Design system: "study paper" theme. Use `mode-*` colors (`mode-flashcards`, `mode-analytics`, `mode-library`, `mode-quizzes`), `font-display`, `font-mono`, `shadow-sheet`, `rise` entrance animation, hairline-divided panels (`gap-px` over a `bg-slate-100` backing). Match the existing analytics/flashcards pages.
- Never render a card's question text on the home page — the due block shows counts only, as the analytics endpoint already enforces server-side.
- Frontend file/line references and pure-module test pattern follow the existing codebase; do not add a JS test framework.
- Commit after each task. Branch: `feat/local-llm-generation` (current).

---

### Task 1: Streak advances when a card is reviewed

The streak is fully modelled but never moves: its only trigger is ending a `StudySession`, which the review flow never creates. Extract the day-math into the pure scheduling module, have the model delegate, and call it from the review path.

**Files:**
- Modify: `backend/study_sessions/scheduling.py` (add `Streak` + `advance_streak`)
- Modify: `backend/study_sessions/models.py` (`StudyStreak.update_streak` delegates; `CardReview.record` updates the streak)
- Test: `tests/test_spaced_repetition.py` (add streak cases)

**Interfaces:**
- Produces: `scheduling.advance_streak(current: int, best: int, last_date: date | None, today: date) -> scheduling.Streak` where `Streak = NamedTuple(current: int, best: int, last_date: date)`.
- Consumes: `scheduling` is already imported by `models.py` and by `tests/test_spaced_repetition.py` (as `sm2`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_spaced_repetition.py` (it already loads the module as `sm2` and imports `date`, `timedelta`):

```python
# ---- advance_streak --------------------------------------------------------
# The streak counts consecutive local days with at least one review. Its math
# is pure here so it can be tested without a database; the model delegates to it.

def test_first_ever_review_starts_a_streak_of_one():
    s = sm2.advance_streak(current=0, best=0, last_date=None, today=TODAY)
    assert (s.current, s.best, s.last_date) == (1, 1, TODAY)


def test_a_second_review_the_same_day_changes_nothing():
    s = sm2.advance_streak(current=3, best=5, last_date=TODAY, today=TODAY)
    assert (s.current, s.best, s.last_date) == (3, 5, TODAY)


def test_a_review_the_next_day_extends_the_streak():
    s = sm2.advance_streak(current=3, best=5, last_date=TODAY, today=TODAY + timedelta(days=1))
    assert s.current == 4
    assert s.last_date == TODAY + timedelta(days=1)


def test_extending_past_the_record_raises_the_best():
    s = sm2.advance_streak(current=5, best=5, last_date=TODAY, today=TODAY + timedelta(days=1))
    assert s.current == 6
    assert s.best == 6


def test_a_gap_of_two_days_restarts_the_streak():
    s = sm2.advance_streak(current=9, best=9, last_date=TODAY, today=TODAY + timedelta(days=2))
    assert s.current == 1
    assert s.best == 9  # the record survives a broken streak
    assert s.last_date == TODAY + timedelta(days=2)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_spaced_repetition.py -k advance_streak -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'advance_streak'`

- [ ] **Step 3: Add the pure function to `scheduling.py`**

At the top, extend the imports and add the type + function (place `advance_streak` after `next_due_batch`):

```python
# (imports already include: from datetime import date; from typing import NamedTuple)


class Streak(NamedTuple):
    current: int
    best: int
    last_date: date


def advance_streak(current: int, best: int, last_date: date | None, today: date) -> Streak:
    """Advance a study streak by one day of activity.

    A streak counts consecutive local days with at least one review. The record
    (`best`) survives a broken streak. Same-day repeats leave everything alone,
    so this is safe to call on every review rather than only the first.
    """
    if last_date is None:
        return Streak(1, max(best, 1), today)
    delta = (today - last_date).days
    if delta == 0:
        return Streak(current, best, last_date)
    if delta == 1:
        current += 1
        return Streak(current, max(best, current), today)
    # A gap (or a clock that moved backwards) restarts the count; the best holds.
    return Streak(1, max(best, 1), today)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_spaced_repetition.py -k advance_streak -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Delegate the model method and wire the review path**

In `backend/study_sessions/models.py`, replace the body of `StudyStreak.update_streak` with a delegation (keep the signature):

```python
    def update_streak(self, session_date):
        """Update streak based on session date (a date or datetime)."""
        if session_date is None:
            return
        if hasattr(session_date, 'date'):
            session_date = session_date.date()
        result = scheduling.advance_streak(
            self.current_streak, self.best_streak, self.last_session_date, session_date
        )
        self.current_streak = result.current
        self.best_streak = result.best
        self.last_session_date = result.last_date
        self.save()
```

Then, in `CardReview.record`, advance the streak after the review is saved (insert before `return review`):

```python
        review.calculate_next_review()
        streak, _ = StudyStreak.objects.get_or_create(user=user)
        streak.update_streak(timezone.localdate())
        return review
```

`StudyStreak` is defined above `CardReview` in the same file and `timezone` is already imported, so no new imports are needed.

- [ ] **Step 6: Run the full backend-facing suite**

Run: `python -m pytest tests/test_spaced_repetition.py -v`
Expected: PASS (all streak + scheduling tests green)

Then confirm Django is happy: `cd backend && ./venv/bin/python manage.py check`
Expected: no errors.

- [ ] **Step 7: Smoke-test the wiring against the real DB**

The wiring itself (record → streak) is DB-bound and there is no Django test DB in this repo, so verify it once by hand and clean up:

```bash
cd backend && ./venv/bin/python manage.py shell <<'PY'
from django.contrib.auth.models import User
from flashcards.models import Flashcard
from study_sessions.models import CardReview, StudyStreak
u, _ = User.objects.get_or_create(username="__streak_smoke__")
fc = Flashcard.objects.create(user=u, question="Q?", answer="A", difficulty="easy")
CardReview.record(u, fc, "good")
CardReview.record(u, fc, "good")  # same day again -> no change
s = StudyStreak.objects.get(user=u)
print("current:", s.current_streak, "best:", s.best_streak, "last:", s.last_session_date)
CardReview.objects.filter(user=u).delete(); fc.delete(); StudyStreak.objects.filter(user=u).delete(); u.delete()
PY
```

Expected: `current: 1 best: 1 last: <today>`

- [ ] **Step 8: Commit**

```bash
git add backend/study_sessions/scheduling.py backend/study_sessions/models.py tests/test_spaced_repetition.py
git commit -m "feat(study): advance the study streak when a card is reviewed"
```

---

### Task 2: Frontend API clients for streak and weekly stats

The home page needs the streak and the 7-day review stats. Both endpoints exist; only client methods are missing.

**Files:**
- Modify: `lib/api.ts`

**Interfaces:**
- Produces: `streaksAPI.getMe()` → `GET /study/streaks/me/`; `reviewsAPI.getWeeklyStats()` → `GET /study/card-reviews/stats/`.
- Consumes: the existing `api` axios instance and `flashcardsAPI` block for placement.

- [ ] **Step 1: Add the client methods**

In `lib/api.ts`, after the `flashcardsAPI` block, add:

```typescript
export const streaksAPI = {
  // Current/best consecutive-day streak. Advances when a card is reviewed.
  getMe: () => api.get('/study/streaks/me/'),
}

export const reviewsAPI = {
  // Reviews done and recall accuracy over the last 7 days — a real week window,
  // unlike the all-time counts on the analytics summary.
  getWeeklyStats: () => api.get('/study/card-reviews/stats/'),
}
```

- [ ] **Step 2: Verify the types compile**

Run: `./node_modules/.bin/tsc --noEmit`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add lib/api.ts
git commit -m "feat(api): client methods for study streak and weekly review stats"
```

---

### Task 3: Extract the due-count formatting so Home and Analytics share it

The Home due block shows the same count, breakdown, and caught-up message as Analytics. Extract those two functions to a shared module so the two pages cannot drift, then point Analytics at it (behavior-preserving — no wording change).

**Files:**
- Create: `lib/study-format.ts`
- Modify: `app/dashboard/analytics/page.tsx` (import instead of defining locally)

**Interfaces:**
- Produces: `type Due` and `dueBreakdown(d: Due): string` and `caughtUpMessage(d: Due): string`, moved verbatim from `app/dashboard/analytics/page.tsx`.
- Consumes: nothing external.

- [ ] **Step 1: Create the shared module**

Create `lib/study-format.ts` with the `Due` type and the two functions exactly as they currently exist in `app/dashboard/analytics/page.tsx` (move, do not rewrite):

```typescript
/** How much study the schedule says is owed. Counts only — questions belong on
 *  the study page, since reading one here is a free look at a card minutes
 *  before you grade your recall of it. */
export type Due = {
  due: number
  overdue: number
  new: number
  next_date: string | null
  next_count: number
}

/** What the ready-to-study number is made of, worst news first. */
export function dueBreakdown(d: Due): string {
  const parts: string[] = []
  if (d.overdue) parts.push(`${d.overdue} overdue`)
  if (d.due) parts.push(`${d.due} due`)
  if (d.new) parts.push(`${d.new} new`)
  return parts.join(' · ')
}

/** An empty queue is the schedule working. Saying only "nothing due" makes that
 *  read exactly like a schedule that's broken, so name the day cards return. */
export function caughtUpMessage(d: Due): string {
  if (!d.next_date || d.next_count === 0) {
    return 'Nothing to study yet — generate flashcards from a notebook to start.'
  }
  const when = new Date(`${d.next_date}T00:00:00`)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const days = Math.round((when.getTime() - today.getTime()) / 86_400_000)
  const label =
    days === 1
      ? 'tomorrow'
      : `on ${when.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}`
  return `Caught up — nothing due today. ${d.next_count} card${
    d.next_count === 1 ? '' : 's'
  } return ${label}.`
}
```

- [ ] **Step 2: Point Analytics at the shared module**

In `app/dashboard/analytics/page.tsx`, delete the local `type Due`, `dueBreakdown`, and `caughtUpMessage` definitions, and add near the top imports:

```typescript
import { type Due, dueBreakdown, caughtUpMessage } from '@/lib/study-format'
```

Leave every use of `due`, `dueBreakdown(due)`, and `caughtUpMessage(due)` untouched.

- [ ] **Step 3: Verify it compiles unchanged**

Run: `./node_modules/.bin/tsc --noEmit`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add lib/study-format.ts app/dashboard/analytics/page.tsx
git commit -m "refactor(analytics): extract due-count formatting for reuse on Home"
```

---

### Task 4: The Today home page

Replace the `/dashboard` redirect with the Today page: greeting + streak, the due block (primary), weekly stats, recent notebooks, and top weak documents. A brand-new user (no notebooks) collapses to a single create hero.

**Files:**
- Modify: `app/dashboard/page.tsx` (replace the redirect entirely)

**Interfaces:**
- Consumes: `analyticsAPI.getRecommendations()` (`{ due: Due, weak_sources: [] }`), `reviewsAPI.getWeeklyStats()` (`{ reviews_this_week, accuracy_this_week_percent }`), `streaksAPI.getMe()` (`{ current_streak, best_streak }`), `notebooksAPI.getNotebooks()` (`[{ id, title }]`), and `Due`/`dueBreakdown`/`caughtUpMessage` from `@/lib/study-format`.
- Produces: the route; nothing imports from it.

- [ ] **Step 1: Replace the redirect with the page**

Overwrite `app/dashboard/page.tsx` with:

```tsx
'use client'

import Link from 'next/link'
import useSWR from 'swr'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { analyticsAPI, notebooksAPI, reviewsAPI, streaksAPI } from '@/lib/api'
import { type Due, dueBreakdown, caughtUpMessage } from '@/lib/study-format'
import { cn } from '@/lib/utils'
import { ArrowRight, Flame, NotebookText, Target, Zap } from 'lucide-react'

type Notebook = { id: number; title: string }
type WeakSource = { source_id: number; title: string; accuracy: number | null }

function greeting(d = new Date()): string {
  const h = d.getHours()
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

export default function HomePage() {
  const { data: recsRes } = useSWR(['/analytics/recommendations'], () =>
    analyticsAPI.getRecommendations()
  )
  const { data: weekRes } = useSWR(['/study/weekly-stats'], () => reviewsAPI.getWeeklyStats())
  const { data: streakRes } = useSWR(['/study/streak'], () => streaksAPI.getMe())
  const { data: notebooksRes } = useSWR(['/notebooks/all'], () => notebooksAPI.getNotebooks())

  const due: Due = recsRes?.data?.due ?? {
    due: 0,
    overdue: 0,
    new: 0,
    next_date: null,
    next_count: 0,
  }
  const ready = due.due + due.new
  const weakSources: WeakSource[] = (recsRes?.data?.weak_sources ?? []).slice(0, 3)
  const reviewsThisWeek: number = weekRes?.data?.reviews_this_week ?? 0
  const accuracyThisWeek: number | null = weekRes?.data?.accuracy_this_week_percent ?? null
  const streak: number = streakRes?.data?.current_streak ?? 0
  const bestStreak: number = streakRes?.data?.best_streak ?? 0
  const notebooks: Notebook[] = (
    notebooksRes?.data?.results ??
    notebooksRes?.data ??
    []
  ).slice(0, 4)

  const hasAnything = notebooks.length > 0

  return (
    <div className="max-w-5xl space-y-8">
      {/* Greeting + streak */}
      <div className="rise flex flex-wrap items-end justify-between gap-4 border-t-[3px] border-mode-library pt-4">
        <div>
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.14em] text-mode-library">
            Today
          </p>
          <h1 className="mt-1 font-display text-3xl font-semibold text-slate-900 md:text-4xl">
            {greeting()}
          </h1>
        </div>
        {streak > 0 ? (
          <div className="flex items-center gap-2 rounded-full bg-amber-50 px-4 py-2 text-amber-900">
            <Flame className="size-5 text-amber-500" />
            <span className="font-mono text-sm tabular-nums">
              {streak} day streak{bestStreak > streak ? ` · best ${bestStreak}` : ''}
            </span>
          </div>
        ) : (
          <p className="font-mono text-sm text-slate-500">Study today to start a streak.</p>
        )}
      </div>

      {!hasAnything ? (
        <Card className="rise flex flex-col items-center gap-4 border-slate-200 p-12 text-center shadow-sheet">
          <NotebookText className="size-14 text-slate-300" />
          <p className="text-xl text-slate-600">Create your first notebook to start studying.</p>
          <Button
            asChild
            size="lg"
            className="h-12 bg-mode-library text-lg text-white hover:bg-mode-library-hover"
          >
            <Link href="/dashboard/notebooks">New notebook</Link>
          </Button>
        </Card>
      ) : (
        <>
          {/* Due today (primary) + this week */}
          <div className="grid gap-6 md:grid-cols-3">
            <Card
              className="rise border-slate-200 p-6 shadow-sheet md:col-span-2"
              style={{ animationDelay: '60ms' }}
            >
              {ready === 0 ? (
                <div className="flex items-center gap-3 py-2">
                  <Target className="size-5 shrink-0 text-mode-analytics" />
                  <p className="text-lg text-slate-700">{caughtUpMessage(due)}</p>
                </div>
              ) : (
                <div className="flex flex-wrap items-center justify-between gap-5">
                  <div className="flex min-w-0 items-baseline gap-4">
                    <span className="font-mono text-5xl font-semibold tabular-nums text-slate-900">
                      {ready}
                    </span>
                    <div className="min-w-0">
                      <p className="text-lg text-slate-900">
                        card{ready === 1 ? '' : 's'} due today
                      </p>
                      <p
                        className={cn(
                          'font-mono text-sm tabular-nums',
                          due.overdue > 0 ? 'text-red-700' : 'text-slate-500'
                        )}
                      >
                        {dueBreakdown(due)}
                      </p>
                    </div>
                  </div>
                  <Button
                    asChild
                    size="lg"
                    className="h-12 shrink-0 bg-mode-flashcards px-8 text-lg text-white hover:bg-mode-flashcards-hover"
                  >
                    <Link href="/dashboard/flashcards?due=1">
                      Study now
                      <ArrowRight className="ml-2 size-5" />
                    </Link>
                  </Button>
                </div>
              )}
            </Card>

            <Card
              className="rise border-slate-200 p-6 shadow-sheet"
              style={{ animationDelay: '120ms' }}
            >
              <div className="mb-3 flex items-center gap-2 text-slate-500">
                <Zap className="size-4 text-mode-flashcards" />
                <span className="text-sm">This week</span>
              </div>
              <p className="font-mono text-3xl font-semibold tabular-nums text-slate-900">
                {reviewsThisWeek}
              </p>
              <p className="text-sm text-slate-500">
                review{reviewsThisWeek === 1 ? '' : 's'}
                {accuracyThisWeek != null ? ` · ${accuracyThisWeek}% recalled` : ''}
              </p>
            </Card>
          </div>

          {/* Jump back in + weakest right now */}
          <div className="grid gap-6 md:grid-cols-2">
            <Card
              className="rise border-slate-200 p-6 shadow-sheet"
              style={{ animationDelay: '180ms' }}
            >
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <NotebookText className="size-5 text-mode-library" />
                  <h2 className="text-xl font-semibold text-slate-900">Jump back in</h2>
                </div>
                <Link
                  href="/dashboard/notebooks"
                  className="shrink-0 text-sm font-medium text-mode-library hover:underline"
                >
                  All notebooks →
                </Link>
              </div>
              <ul className="divide-y divide-slate-100">
                {notebooks.map((n) => (
                  <li key={n.id}>
                    <Link
                      href={`/dashboard/notebooks/${n.id}`}
                      className="flex items-center gap-3 py-3 text-slate-800 hover:text-mode-library"
                    >
                      <NotebookText className="size-4 shrink-0 text-slate-400" />
                      <span className="truncate">{n.title}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>

            <Card
              className="rise border-slate-200 p-6 shadow-sheet"
              style={{ animationDelay: '240ms' }}
            >
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Target className="size-5 text-mode-analytics" />
                  <h2 className="text-xl font-semibold text-slate-900">Weakest right now</h2>
                </div>
                <Link
                  href="/dashboard/analytics"
                  className="shrink-0 text-sm font-medium text-mode-analytics hover:underline"
                >
                  Analytics →
                </Link>
              </div>
              {weakSources.length === 0 ? (
                <p className="py-3 text-slate-500">
                  Study a document and its recall shows up here.
                </p>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {weakSources.map((s) => (
                    <li key={s.source_id} className="flex items-center gap-4 py-3">
                      <span className="min-w-0 flex-1 truncate text-slate-800">{s.title}</span>
                      <span className="shrink-0 font-mono text-sm tabular-nums text-slate-600">
                        {s.accuracy == null ? 'Not studied' : `${s.accuracy}%`}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify it compiles**

Run: `./node_modules/.bin/tsc --noEmit`
Expected: exit 0.

- [ ] **Step 3: Verify the route renders against the running app**

With backend (`:8000`) and frontend (`:3000`) running, open `http://localhost:3000/dashboard` while logged in.
Expected: the Today page renders; the due block matches the count on `/dashboard/analytics`; recent notebooks link through; no card question text appears anywhere on the page.

- [ ] **Step 4: Commit**

```bash
git add app/dashboard/page.tsx
git commit -m "feat(dashboard): Today home page over existing study data"
```

---

### Task 5: Home in the sidebar

Add a Home entry to the nav and point the brand mark at `/dashboard`, so the new page is reachable and is where the logo leads.

**Files:**
- Modify: `components/dashboard-sidebar.tsx`

**Interfaces:**
- Consumes: the existing `navItems` array and `BrandMark`/`SidebarBody` structure.

- [ ] **Step 1: Add the Home nav item**

In `components/dashboard-sidebar.tsx`, import `Home` from lucide-react (add to the existing import block) and prepend a Home entry to `navItems`:

```tsx
const navItems: NavItem[] = [
  {
    href: '/dashboard',
    label: 'Home',
    icon: Home,
    activeClass: 'bg-mode-library/10 text-mode-library',
  },
  {
    href: '/dashboard/notebooks',
    label: 'Notebooks',
    icon: NotebookText,
    activeClass: 'bg-mode-library/10 text-mode-library',
  },
  {
    href: '/dashboard/analytics',
    label: 'Analytics',
    icon: BarChart3,
    activeClass: 'bg-mode-analytics/10 text-mode-analytics',
  },
]
```

- [ ] **Step 2: Fix the active-state match for Home**

`useIsActive` treats a prefix match as active, so `/dashboard` would light up on every sub-route. Change the Home comparison to exact-only by updating `useIsActive` to special-case the dashboard root:

```tsx
function useIsActive() {
  const pathname = usePathname()
  return (href: string) => {
    if (href === '/dashboard') return pathname === '/dashboard'
    return pathname === href || (pathname?.startsWith(href + '/') ?? false)
  }
}
```

- [ ] **Step 3: Point the brand mark and mobile logo at `/dashboard`**

In the same file, change both `<Link href="/dashboard/notebooks">` used by the brand (in `SidebarBody`) and the mobile logo (in `MobileNavBar`) to `href="/dashboard"`.

- [ ] **Step 4: Verify it compiles and behaves**

Run: `./node_modules/.bin/tsc --noEmit`
Expected: exit 0.

Then in the running app: Home is highlighted only on `/dashboard`, not on `/dashboard/notebooks` or `/dashboard/analytics`; the logo leads to the Today page.

- [ ] **Step 5: Commit**

```bash
git add components/dashboard-sidebar.tsx
git commit -m "feat(nav): add Home to the sidebar and point the brand at it"
```

---

## Final verification

- [ ] `python -m pytest -q` — all backend tests pass.
- [ ] `./node_modules/.bin/tsc --noEmit` — exit 0.
- [ ] `cd backend && ./venv/bin/python manage.py check` — no errors.
- [ ] Manual: log in, land on `/dashboard`; grade a due card and confirm the streak chip appears/advances; confirm the due count matches Analytics and no question text shows on Home.
