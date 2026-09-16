# Language Switch (English / Tiếng Việt) — Design

**Date:** 2026-09-17
**Status:** Implemented 2026-09-17
**Author:** pairing session

## Problem

Every word the app shows is English. The people it is built for are
Vietnamese university students, and the person building it reads the product
in Vietnamese. There is no way to change that, and no place where it *could*
change: strings sit inline in 27 components, error messages are literals in
Django views, the reminder email is a hard-coded English template.

One thing already exists and is unused: `UserProfile.preferred_language`
(`CharField`, default `'en'`). Nothing reads it, nothing writes it.

## Goals

- A switch between **English** and **Tiếng Việt** that applies to every
  string the app itself produces: interface text, the reminder email, and
  the `detail` messages the API returns for the student to read.
- The choice follows the **account** (`preferred_language`), so it holds
  across devices and the reminder email speaks the right language; before
  sign-in, the browser's language decides.
- No flash of the wrong language: the server renders in the chosen language
  from the first byte.
- Vietnamese copy in the product's own voice — calm, plain, no
  machine-translation stiffness — written by hand, reviewed by the user.

## Non-goals

- Translating **generated content**. Flashcards and quiz questions come out
  in the language of the source document, as they do now. (The extractive
  ML path is English-only spaCy; that limit is unchanged.)
- Locale-prefixed URLs (`/vi/dashboard`). One URL space; the language is a
  preference, not a route.
- More than two languages. The mechanism allows it; the copy is the work,
  and only these two are written.
- Translating Django admin.

## Design

### Where the language comes from

One source of truth per state, and one place that turns it into a request
locale:

| State | Locale source |
|---|---|
| Signed out | `Accept-Language` header, mapped to `en`/`vi`, default `en` |
| Signed in | `UserProfile.preferred_language` |

The frontend mirrors the effective locale into a cookie **`lang`** (`en` or
`vi`, one year, `SameSite=Lax`). The Next.js server reads that cookie to pick
the message catalogue and the `<html lang>` for **server rendering** — this
is what prevents the flash. The dashboard layout, which already syncs the
browser timezone to the profile once per session, does the mirror: after
sign-in it reads `preferred_language` from `/users/profiles/me/`; if it
differs from the cookie, it sets the cookie and calls `router.refresh()`.

Switching: the control writes the cookie, PUTs `preferred_language` when
signed in, and refreshes. The API call may fail (offline); the cookie still
wins locally and the next session re-syncs from the profile.

### Frontend: `next-intl` without routing

- `i18n/request.ts` — `getRequestConfig` reads the `lang` cookie (falling
  back to `Accept-Language`, then `en`) and loads `messages/<locale>.json`.
- `next.config.mjs` — wrapped with `createNextIntlPlugin('./i18n/request.ts')`.
- `app/layout.tsx` — `<html lang={locale}>`, children inside
  `<NextIntlClientProvider>`.
- Components call `useTranslations('<namespace>')` and `t('key')`. Namespaces
  are by surface: `common`, `nav`, `auth`, `home`, `notebooks`, `flashcards`,
  `quizzes`, `tests`, `analytics`, `profile`. Keys are camelCase, named for
  meaning (`startNow`, `notYetOpens`), never for the English text.
- Plurals through ICU in the English catalogue
  (`{count, plural, one {# card} other {# cards}}`); Vietnamese has no
  plural inflection, so `{count} thẻ`. The hand-rolled
  `card${n === 1 ? '' : 's'}` patterns go away.
- Dates and weekdays: `useFormatter()` / `Intl` with the active locale, in
  place of `toLocaleDateString(undefined, …)`. The activity strip's weekday
  initials and the reminder time in the email follow the language.
- Server components (`app/layout.tsx`, `app/page.tsx` if any text) use
  `getTranslations`.

### The switch

A two-segment control **EN · VI** (each segment shows its own name in its own
language: "English", "Tiếng Việt"), `role="radiogroup"`, keyboard-operable,
placed:

- in the dashboard sidebar footer, next to the sign-out control;
- on the login and register pages, top-right of the form.

No flags. No globe icon on its own — the segments are the label.

### Backend: Django's own i18n

- `settings.py`: `LANGUAGES = [('en', 'English'), ('vi', 'Tiếng Việt')]`,
  `LOCALE_PATHS = [BASE_DIR / 'locale']`, `LocaleMiddleware` after
  `SessionMiddleware`. `LANGUAGE_CODE` stays `en-us`.
- The frontend's axios client sends `Accept-Language: <lang cookie>` on
  every request; `LocaleMiddleware` activates it. The 25 user-facing
  `detail` strings in views are wrapped in `gettext` (`_()`); error messages
  meant for developers (`ensure_ml_model`, 503 text) stay English.
- `backend/locale/vi/LC_MESSAGES/django.po` is committed; `django.mo` is
  compiled at setup (`manage.py compilemessages`, added to the README setup
  list) and gitignored. The dev database is unaffected.
- `UserProfileSerializer.preferred_language` validates against `LANGUAGES`
  (today it accepts any 10-char string).

### The reminder email

`reminder_email.build_reminder` is deliberately Django-free and stays so: it
gains a `lang` argument and carries both templates itself. The command
passes `plan.user.profile.preferred_language` and formats the time with the
student's zone (already) and language (new: the month name). Vietnamese
copy:

> Bạn đã lên lịch một bài thi thử cho *{notebook}*.
> Khi nào: 16 tháng 9 2026 lúc 15:00 +07
> Đề: 20 câu, 30 phút
> Làm bài tại: {url}
> — StudyFlow

Subject: *Bài thi thử {notebook} sắp tới*.

### Error handling

- Missing key in a catalogue → next-intl renders the key path in
  development and logs; a parity test (below) keeps that from shipping.
- Unknown cookie value → treated as `en`.
- Profile PUT with a language outside `LANGUAGES` → 400.
- `django.mo` missing (setup step skipped) → English strings; nothing
  breaks. The README and `ensure_ml_model`-style check make it visible.

## Testing

- **Catalogue parity (pure, `tests/test_messages_parity.py`)**: every key in
  `messages/en.json` exists in `messages/vi.json` and vice versa; every ICU
  placeholder used in an English message appears in the Vietnamese one.
  This is the test that fails when someone adds a string to one side only.
- **Reminder email (pure)**: `build_reminder(..., lang='vi')` yields the
  Vietnamese subject and body with the time in Vietnamese month form;
  unknown `lang` falls back to English.
- **API (`backend/tests`)**: `Accept-Language: vi` on a request that 400s
  returns the Vietnamese `detail`; `en` (and no header) returns English;
  profile PUT accepts `vi`, rejects `fr`; the reminder command sends the
  Vietnamese email to a `vi` profile.
- **Frontend**: `tsc` and `pnpm lint` clean; a screenshot pass of login,
  dashboard home, one notebook, flashcards, quizzes, tests, analytics in
  Vietnamese at 1100px and 400px — Vietnamese runs ~30% longer than English
  and breaks layouts that were sized to English.
- **Manual**: switch on the sidebar → whole app changes with no flash;
  reload → still Vietnamese; sign out → browser language; sign in on the
  API with the profile set to `vi` → reminder email arrives in Vietnamese.

## Out of scope, noted for later

- Vietnamese generated content (needs a `language` hint in the generation
  prompts and a non-spaCy fallback).
- Translating the mock-test paper's own labels inside stored questions
  (question text is content, not chrome).
- A third language: add `messages/<code>.json`, a `.po`, and the
  `LANGUAGES` entry; the switch grows a segment.

## Notes from implementation

- Left in English on purpose: "StudyFlow", "Email" (a loanword), file-format
  names (PDF · Word (.docx) · PowerPoint (.pptx)), the `(r)` key hint, and
  `app/developer` (a developer-only page of links).
- True/False quiz options are stored as the English words the grader
  compares against; only their display is translated (`optionLabel`).
- The parity test learned three things the design did not anticipate: an
  ICU plural *selector* may be dropped in Vietnamese when the number is
  shown elsewhere; words inside a plural branch are not placeholders; a
  message made only of placeholders has nothing to translate.
- Vietnamese "narrow" weekdays come out as T2…CN from `Intl`, which is the
  right label for the activity strip.
- Generation error messages that pass through `str(exc)` are translated
  only for the source guard ("too short…", the one students meet); provider
  failures stay as raised.
