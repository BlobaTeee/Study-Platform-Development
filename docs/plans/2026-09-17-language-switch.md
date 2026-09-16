# Language Switch (EN / VI) Implementation Plan

**Goal:** Every string the app itself produces — interface, API `detail` messages, the reminder email — can be shown in English or Vietnamese, chosen per account, with the server rendering the right language from the first byte.

**Architecture:** `next-intl` without locale routing on the frontend, reading a `lang` cookie that mirrors `UserProfile.preferred_language`; Django's own `gettext` + `LocaleMiddleware` on the backend, driven by an `Accept-Language` header the axios client sets from the same cookie. The reminder email stays Django-free and carries both languages itself. A parity test keeps the two catalogues in step.

**Tech Stack:** next-intl 4.14 (Next 16 App Router, React 19), ICU messages; Django 5.2 i18n (`makemessages`/`compilemessages`, gettext via Homebrew); pytest.

**Spec:** `docs/specs/2026-09-17-language-switch-design.md`

## Global Constraints

- Branch `feat/language-switch` off `feat/ml-dataset-registry` @ `8370f37` (short-answer mode included).
- Pure tests: `.venv/bin/pytest -q` (repo root). API tests: `cd backend && ./venv/bin/pytest -q`. Frontend: `./node_modules/.bin/tsc --noEmit -p tsconfig.json` and `pnpm lint` (0 errors).
- **Keys are named for meaning, never for the English text**: `startNow`, `notYetOpens`, `reminderSent` — not `start_now_button_text`. camelCase. One namespace per surface: `common`, `nav`, `auth`, `home`, `notebooks`, `flashcards`, `quizzes`, `tests`, `analytics`, `profile`.
- **Plurals only through ICU** in `en.json` (`{count, plural, one {# card} other {# cards}}`); the Vietnamese message is the singular form with the number (`{count} thẻ`). Delete every hand-rolled `${n === 1 ? '' : 's'}` you touch.
- **Every string moved gets both languages in the same task.** `tests/test_messages_parity.py` fails otherwise.
- Vietnamese copy follows PRODUCT.md's voice: calm, plain, second person "bạn", no exclamation marks, no "Vui lòng" on buttons. Use the glossary below; do not invent a second term for something already in it.
- Layout check: Vietnamese runs ~30% longer. After each frontend task, look at the surface at 1100px and 400px (the preview harness under `app/preview-*` is fine, deleted before commit) for truncation, wrapped buttons, overflowing chips.

### Glossary (EN → VI) — use exactly these

| English | Vietnamese | Note |
|---|---|---|
| notebook | sổ tay | the container |
| source / document | tài liệu | never "nguồn" |
| flashcard / card | thẻ | "thẻ ghi nhớ" only in a title |
| quiz | bài kiểm tra | |
| mock test / test | thi thử / bài thi thử | "Tests" nav item → "Thi thử" |
| planned test / plan | lịch thi thử | |
| review (a card) | ôn | "ôn thẻ" |
| grade (self) | chấm | |
| due / due today | đến hạn / đến hạn hôm nay | |
| overdue | quá hạn | |
| recall / recalled | nhớ / nhớ được | "recall accuracy" → "tỉ lệ nhớ" |
| generate | tạo | not "sinh" in the UI |
| Study now | Ôn ngay | |
| Start now | Bắt đầu ngay | |
| Check answer | Kiểm tra | |
| Next question | Câu tiếp | |
| Finish | Hoàn thành | |
| Correct / Close / Not quite | Đúng / Gần đúng / Chưa đúng | typed-mode verdicts |
| I was right | Tôi đúng mà | |
| Type answers | Gõ câu trả lời | |
| Analytics / Your progress | Tiến độ / Tiến độ của bạn | nav item "Tiến độ" |
| Last 14 days | 14 ngày qua | |
| Weakest first | Yếu nhất trước | |
| Reminder | Nhắc | "Nhắc trước 1 giờ" |
| Sign in / Sign out / Sign up | Đăng nhập / Đăng xuất / Đăng ký | |
| Loading… | Đang tải… | |
| Cancel | Hủy | |
| Delete | Xóa | |
| Save | Lưu | |
| Sources (nav) | Tài liệu | |
| Hard / Good / Easy | Khó / Được / Dễ | SM-2 grades |
| Sat (a plan) | Đã thi | |

---

### Task 1: Frontend i18n infrastructure + catalogue parity test

**Files:**
- Create: `i18n/request.ts`, `i18n/locale.ts`, `messages/en.json`, `messages/vi.json`, `components/language-switch.tsx`
- Modify: `next.config.mjs`, `app/layout.tsx`, `lib/api.ts:6-20`, `app/dashboard/layout.tsx` (after the timezone effect)
- Test: `tests/test_messages_parity.py`

**Interfaces:**
- Produces: `LANG_COOKIE = 'lang'`, `type Locale = 'en' | 'vi'`, `readLocaleCookie(): Locale | null`, `writeLocaleCookie(locale)` (client, `i18n/locale.ts`); `<LanguageSwitch />` (client component; props `{ compact?: boolean }`); messages available via `useTranslations(ns)` in every client component under the root layout; `Accept-Language` on every API call.

- [ ] **Step 1: Parity test first**

`tests/test_messages_parity.py`:

```python
"""The two message catalogues describe the same interface.

A key present on one side only renders as its own path in the other
language; a placeholder present on one side only breaks formatting. Both
are caught here rather than by a Vietnamese-speaking user.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "messages"
PLACEHOLDER = re.compile(r"\{(\w+)")


def _flat(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flat(v, key + "."))
        else:
            out[key] = v
    return out


def _load(name):
    return _flat(json.loads((ROOT / f"{name}.json").read_text()))


def test_every_english_key_has_a_vietnamese_one_and_vice_versa():
    en, vi = _load("en"), _load("vi")
    assert set(en) - set(vi) == set(), f"missing in vi.json: {sorted(set(en) - set(vi))}"
    assert set(vi) - set(en) == set(), f"missing in en.json: {sorted(set(vi) - set(en))}"


def test_placeholders_match():
    en, vi = _load("en"), _load("vi")
    for key in en:
        assert set(PLACEHOLDER.findall(en[key])) == set(PLACEHOLDER.findall(vi[key])), key


def test_no_message_is_left_empty_or_untranslated():
    en, vi = _load("en"), _load("vi")
    for key in en:
        assert en[key].strip() and vi[key].strip(), key
        # A Vietnamese message identical to the English one is allowed only
        # for proper nouns and symbols (StudyFlow, EN, ·).
        if vi[key] == en[key]:
            assert not re.search(r"[a-z]{4,}", en[key]) or en[key] in ("StudyFlow",), key
```

Run: `.venv/bin/pytest tests/test_messages_parity.py -q` — Expected: error, `messages/` missing.

- [ ] **Step 2: Install and seed the catalogues**

Run: `pnpm add next-intl@^4.14`

`messages/en.json` and `messages/vi.json` start with the `common` and `nav` namespaces only (every later task adds its own):

```json
{
  "common": {
    "loading": "Loading…",
    "cancel": "Cancel",
    "delete": "Delete",
    "save": "Save",
    "retry": "Try again",
    "language": "Language",
    "english": "English",
    "vietnamese": "Tiếng Việt",
    "cards": "{count, plural, one {# card} other {# cards}}",
    "questions": "{count, plural, one {# question} other {# questions}}",
    "minutes": "{count, plural, one {# minute} other {# minutes}}"
  },
  "nav": {
    "home": "Home",
    "notebooks": "Notebooks",
    "flashcards": "Flashcards",
    "quizzes": "Quizzes",
    "tests": "Tests",
    "analytics": "Analytics",
    "signOut": "Sign out"
  }
}
```

```json
{
  "common": {
    "loading": "Đang tải…",
    "cancel": "Hủy",
    "delete": "Xóa",
    "save": "Lưu",
    "retry": "Thử lại",
    "language": "Ngôn ngữ",
    "english": "English",
    "vietnamese": "Tiếng Việt",
    "cards": "{count} thẻ",
    "questions": "{count} câu",
    "minutes": "{count} phút"
  },
  "nav": {
    "home": "Trang chủ",
    "notebooks": "Sổ tay",
    "flashcards": "Thẻ",
    "quizzes": "Bài kiểm tra",
    "tests": "Thi thử",
    "analytics": "Tiến độ",
    "signOut": "Đăng xuất"
  }
}
```

Run the parity test: 3 passed.

- [ ] **Step 3: Locale helpers**

`i18n/locale.ts`:

```ts
export const LOCALES = ['en', 'vi'] as const
export type Locale = (typeof LOCALES)[number]
export const DEFAULT_LOCALE: Locale = 'en'
export const LANG_COOKIE = 'lang'

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && (LOCALES as readonly string[]).includes(value)
}

/** Best match for an Accept-Language header, or the default. */
export function localeFromAcceptLanguage(header: string | null | undefined): Locale {
  for (const part of (header ?? '').split(',')) {
    const tag = part.trim().split(';')[0].toLowerCase()
    if (tag.startsWith('vi')) return 'vi'
    if (tag.startsWith('en')) return 'en'
  }
  return DEFAULT_LOCALE
}

// Client-side cookie access. The cookie is the one thing the server reads
// to pick the language, so writing it is how the switch takes effect.
export function readLocaleCookie(): Locale | null {
  if (typeof document === 'undefined') return null
  const match = document.cookie.match(new RegExp(`(?:^|; )${LANG_COOKIE}=([^;]*)`))
  const value = match?.[1]
  return isLocale(value) ? value : null
}

export function writeLocaleCookie(locale: Locale) {
  if (typeof document === 'undefined') return
  document.cookie = `${LANG_COOKIE}=${locale}; Path=/; Max-Age=31536000; SameSite=Lax`
}
```

`i18n/request.ts`:

```ts
import { cookies, headers } from 'next/headers'
import { getRequestConfig } from 'next-intl/server'
import { isLocale, localeFromAcceptLanguage, LANG_COOKIE } from './locale'

// No locale routing: the language is a preference, mirrored into a cookie so
// the server can render it from the first byte. Signed-out visitors get
// their browser's language.
export default getRequestConfig(async () => {
  const cookie = (await cookies()).get(LANG_COOKIE)?.value
  const locale = isLocale(cookie)
    ? cookie
    : localeFromAcceptLanguage((await headers()).get('accept-language'))
  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  }
})
```

- [ ] **Step 4: Wire Next and the root layout**

`next.config.mjs`:

```js
import createNextIntlPlugin from 'next-intl/plugin'

const withNextIntl = createNextIntlPlugin('./i18n/request.ts')

/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
}

export default withNextIntl(nextConfig)
```

In `app/layout.tsx`: add `import { NextIntlClientProvider } from 'next-intl'` and `import { getLocale } from 'next-intl/server'`; make `RootLayout` `async`, `const locale = await getLocale()`, set `lang={locale}` on `<html>`, and wrap the existing `<AuthProvider>` in `<NextIntlClientProvider>` (no props needed — the plugin supplies locale and messages).

- [ ] **Step 5: `Accept-Language` on every API call**

In `lib/api.ts`, inside the existing request interceptor after the `Authorization` line:

```ts
    // The API translates its own messages (Django LocaleMiddleware); tell it
    // which language this browser is showing.
    const lang = readLocaleCookie()
    if (lang) config.headers['Accept-Language'] = lang
```

with `import { readLocaleCookie } from '@/i18n/locale'` at the top.

- [ ] **Step 6: The switch component**

`components/language-switch.tsx`:

```tsx
'use client'

import { useRouter } from 'next/navigation'
import { useLocale, useTranslations } from 'next-intl'
import { useState } from 'react'
import { authAPI } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { cn } from '@/lib/utils'
import { LOCALES, writeLocaleCookie, type Locale } from '@/i18n/locale'

/** EN · VI. Each segment names itself in its own language, so a reader who
 *  cannot read the current one can still find theirs. The cookie is written
 *  first — it is what the server renders from — then the profile, when
 *  signed in, so the choice follows the account. */
export function LanguageSwitch({ compact = false }: { compact?: boolean }) {
  const t = useTranslations('common')
  const locale = useLocale() as Locale
  const router = useRouter()
  const { user } = useAuth()
  const [busy, setBusy] = useState(false)

  const names: Record<Locale, string> = { en: t('english'), vi: t('vietnamese') }
  const short: Record<Locale, string> = { en: 'EN', vi: 'VI' }

  const choose = async (next: Locale) => {
    if (next === locale || busy) return
    setBusy(true)
    writeLocaleCookie(next)
    if (user) {
      try {
        await authAPI.updateProfile({ preferred_language: next })
      } catch {
        /* the cookie still wins locally; the next session re-syncs */
      }
    }
    router.refresh()
    setBusy(false)
  }

  return (
    <div role="radiogroup" aria-label={t('language')} className="inline-flex rounded-md border border-slate-200 bg-white p-0.5">
      {LOCALES.map((code) => {
        const active = code === locale
        return (
          <button
            key={code}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => void choose(code)}
            className={cn(
              'rounded px-2.5 py-1 font-mono text-xs uppercase tracking-wide transition-colors',
              active ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
            )}
            title={names[code]}
          >
            {compact ? short[code] : names[code]}
          </button>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 7: Mirror the profile's language after sign-in**

In `app/dashboard/layout.tsx`, after the timezone effect:

```ts
  // The language follows the account. After sign-in, if the profile says
  // something other than what this browser is showing, adopt it and
  // re-render — the cookie is what the server reads.
  useEffect(() => {
    if (!user) return
    authAPI
      .getProfile()
      .then((res) => {
        const preferred = res.data?.preferred_language
        if (isLocale(preferred) && preferred !== readLocaleCookie()) {
          writeLocaleCookie(preferred)
          router.refresh()
        }
      })
      .catch(() => {})
  }, [user, router])
```

with `import { isLocale, readLocaleCookie, writeLocaleCookie } from '@/i18n/locale'`.

- [ ] **Step 8: Verify**

Run: `./node_modules/.bin/tsc --noEmit -p tsconfig.json && pnpm lint` — 0 errors.
Run: `.venv/bin/pytest -q` — parity tests pass.
With the dev server: `curl -s -H 'Accept-Language: vi' http://localhost:3000/login | grep -o '<html lang="[a-z]*"'` → `lang="vi"`; without the header → `lang="en"`; with `-H 'Cookie: lang=vi'` → `lang="vi"`.

- [ ] **Step 9: Commit**

```bash
git add i18n messages components/language-switch.tsx next.config.mjs app/layout.tsx lib/api.ts app/dashboard/layout.tsx tests/test_messages_parity.py package.json pnpm-lock.yaml
git commit -m "feat(i18n): next-intl without routing, lang cookie, switch component, catalogue parity test"
```

---

### Task 2: Backend — Django i18n, translated `detail` messages, profile validation

**Files:**
- Modify: `backend/studyplatform/settings.py` (`MIDDLEWARE`, `LANGUAGES`, `LOCALE_PATHS`)
- Modify: every view with a user-facing `detail` (list with `grep -rn "'detail':" backend --include='*.py' | grep -v "/venv/\|tests/"`): `quizzes/views.py`, `notebooks/views.py`, `users/…` if any
- Create: `backend/locale/vi/LC_MESSAGES/django.po` (via `makemessages`, then translated by hand)
- Modify: `backend/users/serializers.py` (validate `preferred_language`), `backend/README.md` (setup step), `.gitignore` (`*.mo`)
- Test: `backend/tests/test_i18n.py`

**Interfaces:**
- Produces: API `detail` strings in the request's `Accept-Language`; `preferred_language` accepts only `en`/`vi`.

- [ ] **Step 1: Failing tests**

`backend/tests/test_i18n.py`:

```python
"""The API answers in the language the browser is showing."""
import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def _client(user, lang):
    c = APIClient(HTTP_HOST='localhost', HTTP_ACCEPT_LANGUAGE=lang)
    c.force_authenticate(user)
    return c


def test_a_refused_request_explains_itself_in_vietnamese(user):
    from quizzes.models import Quiz, QuizAttempt
    quiz = Quiz.objects.create(user=user, title='q')
    attempt = QuizAttempt.objects.create(quiz=quiz, user=user)
    res = _client(user, 'vi').post(f'/api/quizzes/attempts/{attempt.id}/grade_typed_answer/',
                                    {'question_id': 1, 'answer': '   '}, format='json')
    assert res.status_code == 400
    assert res.json()['detail'] == 'Hãy gõ câu trả lời trước.'


def test_the_same_request_in_english(user):
    from quizzes.models import Quiz, QuizAttempt
    quiz = Quiz.objects.create(user=user, title='q')
    attempt = QuizAttempt.objects.create(quiz=quiz, user=user)
    res = _client(user, 'en').post(f'/api/quizzes/attempts/{attempt.id}/grade_typed_answer/',
                                    {'question_id': 1, 'answer': '   '}, format='json')
    assert res.json()['detail'] == 'Type an answer first.'


def test_no_header_means_english(client, user):
    from quizzes.models import Quiz, QuizAttempt
    quiz = Quiz.objects.create(user=user, title='q')
    attempt = QuizAttempt.objects.create(quiz=quiz, user=user)
    res = client.post(f'/api/quizzes/attempts/{attempt.id}/grade_typed_answer/',
                      {'question_id': 1, 'answer': '   '}, format='json')
    assert res.json()['detail'] == 'Type an answer first.'


def test_profile_language_accepts_only_the_supported_ones(client, user):
    ok = client.put('/api/users/profiles/update_profile/', {'preferred_language': 'vi'}, format='json')
    assert ok.status_code == 200 and ok.json()['preferred_language'] == 'vi'
    bad = client.put('/api/users/profiles/update_profile/', {'preferred_language': 'fr'}, format='json')
    assert bad.status_code == 400 and 'preferred_language' in bad.json()
```

Run: `cd backend && ./venv/bin/pytest -q tests/test_i18n.py` — Expected: the Vietnamese test and the `fr` rejection fail.

- [ ] **Step 2: Settings**

In `backend/studyplatform/settings.py`, insert `'django.middleware.locale.LocaleMiddleware',` directly after `'django.contrib.sessions.middleware.SessionMiddleware',` in `MIDDLEWARE`, and add after `USE_TZ = True`:

```python
# The API answers in the language the frontend is showing: the axios client
# sends Accept-Language from its `lang` cookie and LocaleMiddleware activates
# it. Translations live in backend/locale/<code>/LC_MESSAGES/django.po;
# `manage.py compilemessages` builds the .mo files (gitignored) at setup.
LANGUAGES = [('en', 'English'), ('vi', 'Tiếng Việt')]
LOCALE_PATHS = [BASE_DIR / 'locale']
```

- [ ] **Step 3: Mark the strings**

In each view file: `from django.utils.translation import gettext as _`, then wrap every `detail` string a student can see: `{'detail': _('Type an answer first.')}`. f-strings become `_('This test opens at %(when)s.') % {'when': …}`. Leave developer-facing ones (`ensure_ml_model`, the 503) unwrapped. Also the `ValidationError` messages in serializers a student can see (`Pick a time in the future.`).

- [ ] **Step 4: Extract, translate, compile**

```bash
cd backend && mkdir -p locale && ./venv/bin/python manage.py makemessages -l vi --ignore=venv
```

Open `backend/locale/vi/LC_MESSAGES/django.po` and fill every `msgstr` by hand, glossary above. Required exact strings (the tests assert them):

| msgid | msgstr |
|---|---|
| `Type an answer first.` | `Hãy gõ câu trả lời trước.` |
| `This attempt is already complete.` | `Lượt làm bài này đã hoàn thành.` |
| `Time is up for this test.` | `Đã hết giờ làm bài.` |
| `This planned test has already been sat.` | `Lịch thi thử này đã được thi.` |
| `This test opens at %(when)s.` | `Bài thi này mở lúc %(when)s.` |
| `Planned test not found.` | `Không tìm thấy lịch thi thử.` |
| `Notebook not found.` | `Không tìm thấy sổ tay.` |
| `Question not part of this quiz.` | `Câu hỏi không thuộc bài kiểm tra này.` |
| `Only typed answers can be overridden.` | `Chỉ câu trả lời tự gõ mới sửa được điểm.` |
| `Pick a time in the future.` | `Chọn một thời điểm trong tương lai.` |
| `No sources selected.` | `Chưa chọn tài liệu nào.` |

(plus the rest of the ~25, same register). Then:

```bash
./venv/bin/python manage.py compilemessages -l vi
```

Add `*.mo` to `.gitignore`. In `backend/README.md` setup list add `venv/bin/python manage.py compilemessages   # API messages in Vietnamese`.

- [ ] **Step 5: Profile validation**

In `UserProfileSerializer`:

```python
    def validate_preferred_language(self, value):
        from django.conf import settings
        codes = [code for code, _ in settings.LANGUAGES]
        if value not in codes:
            raise serializers.ValidationError(f'Unsupported language: {value!r}')
        return value
```

- [ ] **Step 6: Verify and commit**

Run: `cd backend && ./venv/bin/pytest -q` — all pass (62 + 4).

```bash
git add backend/studyplatform/settings.py backend/quizzes/views.py backend/notebooks/views.py backend/quizzes/serializers.py backend/users/serializers.py backend/locale/vi/LC_MESSAGES/django.po backend/README.md .gitignore backend/tests/test_i18n.py
git commit -m "feat(i18n): the API answers in the browser's language"
```

---

### Task 3: The reminder email in Vietnamese

**Files:**
- Modify: `backend/quizzes/services/reminder_email.py`, `backend/quizzes/management/commands/send_test_reminders.py:~120`
- Test: `tests/test_reminder_email.py` (append), `backend/tests/test_send_test_reminders.py` (append)

- [ ] **Step 1: Failing pure test**

Append to `tests/test_reminder_email.py`:

```python
def test_vietnamese_reminder_speaks_vietnamese_including_the_month():
    from datetime import datetime, timezone as tz
    when = datetime(2026, 9, 16, 15, 0, tzinfo=tz(__import__('datetime').timedelta(hours=7)))
    subject, body = reminder_email.build_reminder('Sinh học', when, 20, 30, 'http://x/tests', lang='vi')
    assert subject == 'Bài thi thử Sinh học sắp tới'
    assert 'Khi nào: 16 tháng 9 2026 lúc 15:00 +07' in body
    assert 'Đề: 20 câu, 30 phút' in body
    assert 'Làm bài tại: http://x/tests' in body


def test_unknown_language_falls_back_to_english():
    from datetime import datetime
    subject, _ = reminder_email.build_reminder('Bio', datetime(2026, 9, 16, 15, 0), 20, 30, 'u', lang='xx')
    assert subject == 'Your Bio mock test is coming up'
```

(`reminder_email` is the module the file already loads via importlib; check its name at the top of the file.)

- [ ] **Step 2: Implement**

In `build_reminder`, add `lang: str = 'en'`; keep the English path as is; add:

```python
    if lang == 'vi':
        # Vietnamese dates read "16 tháng 9 2026", not with an English month
        # name; %B would give "September".
        when = f'{scheduled_for.day} tháng {scheduled_for.month} {scheduled_for.year} lúc {scheduled_for:%H:%M}'
        if zone:
            when = f'{when} {zone}'
        subject = f'Bài thi thử {notebook_title} sắp tới'
        body = (
            f'Bạn đã lên lịch một bài thi thử cho {notebook_title}.\n\n'
            f'Khi nào: {when}\n'
            f'Đề: {question_count} câu, {duration_minutes} phút\n\n'
            f'Làm bài tại: {url}\n\n'
            f'— StudyFlow\n'
        )
        return subject, body
```

In the command, pass `lang=getattr(getattr(plan.user, 'profile', None), 'preferred_language', 'en')`.

- [ ] **Step 3: API-level test, then commit**

Append to `backend/tests/test_send_test_reminders.py`:

```python
def test_a_vietnamese_profile_gets_the_vietnamese_reminder(settings, sent, user, notebook):
    settings.EMAIL_BACKEND = SMTP
    user.profile.preferred_language = 'vi'
    user.profile.save(update_fields=['preferred_language'])
    _plan(user, notebook, hours_ahead=0.5)
    _run()
    (subject, body, _, _), = sent
    assert subject.startswith('Bài thi thử')
    assert 'Làm bài tại' in body
```

Run both suites; commit `feat(i18n): the reminder email in the student's language`.

---

### Task 4: Sidebar, dashboard layout chrome, login, register, brand panel

**Files:** `components/dashboard-sidebar.tsx`, `app/dashboard/layout.tsx`, `app/login/page.tsx`, `app/register/page.tsx`, `components/auth-brand-panel.tsx`; `messages/{en,vi}.json` (`nav`, `auth`, `common`)

Procedure for this and every frontend task that follows:

1. Read the file top to bottom. List every user-facing string: JSX text, `placeholder`, `aria-label`, `title`, `alt`, error strings set into state, button labels in ternaries, `document.title`/metadata.
2. Add each to `en.json` under the surface's namespace with a meaning-named key; write the Vietnamese in `vi.json` in the same edit, glossary first.
3. Replace in the component: `const t = useTranslations('<ns>')` (client components) and `t('key')` / `t('key', { count })`. For text with markup inside, use `t.rich('key', { b: (chunks) => <b>{chunks}</b> })`.
4. Delete hand-rolled plural code you touch.
5. Add `<LanguageSwitch compact />` where this task says (sidebar footer; login/register top-right).
6. `tsc`, `pnpm lint`, parity test.
7. Screenshot the surface in `vi` at 1100px and 400px (set `document.cookie='lang=vi'` in the harness or pass the cookie to Playwright) and fix what overflows.
8. Commit: `feat(i18n): <surface> in Vietnamese`.

Namespace plan for this task: `nav` (sidebar items, footer), `auth` (login/register form labels, errors, brand-panel copy), `common`.

- [ ] Steps 1–8 as above for the five files. Reviewer's bar: no English left on the sign-in and sign-up pages or the sidebar in `vi`; the switch works signed out (cookie) and signed in (profile PUT observed in the network tab); `aria-label`s translated too.

---

### Task 5: Home dashboard and notebooks

**Files:** `app/dashboard/page.tsx`, `app/dashboard/notebooks/page.tsx`, `app/dashboard/notebooks/[notebookId]/page.tsx`, `components/notebook-workspace.tsx`, `components/source-drop-zone.tsx`, `components/source-required.tsx`, `components/source-context-banner.tsx`, `components/confirm-dialog.tsx`; namespaces `home`, `notebooks`, `common`.

- [ ] Same procedure. Watch: the workspace's generate buttons and counts ("3 cards · quiz ready"), upload states ("Processing…", "Failed"), the confirm dialog's verb buttons. Vietnamese for "Generate flashcards" is "Tạo thẻ"; "Generate quiz" → "Tạo bài kiểm tra"; "Upload" → "Tải lên"; "Drop a PDF, Word or PowerPoint file" → "Thả file PDF, Word hoặc PowerPoint vào đây".

---

### Task 6: Flashcards study page

**Files:** `app/dashboard/flashcards/page.tsx`, `lib/study-format.ts` (its `dueBreakdown` / `caughtUpMessage` return English — they become functions of `t` or move into the page); namespace `flashcards`.

- [ ] Same procedure. The three grades keep their keyboard hints; "Flip" → "Lật"; "Show answer" → "Xem đáp án"; the "caught up" message → "Đã ôn xong hôm nay. Thẻ tiếp theo đến hạn {date}." Weekday/date formatting through `useFormatter()`.

---

### Task 7: Quizzes page (including typed mode)

**Files:** `app/dashboard/quizzes/page.tsx`; namespace `quizzes`.

- [ ] Same procedure. Verdict words from the glossary; "Check answer" → "Kiểm tra"; the 503 fallback message → "Hiện chưa chấm được câu trả lời tự gõ — hãy chọn đáp án."; "Type your answer" placeholder → "Gõ câu trả lời"; the `(r)` hint stays.

---

### Task 8: Mock tests page

**Files:** `app/dashboard/tests/page.tsx` (the largest — 1,100 lines: setup form, plan form, plan cards, sitting view, review); namespace `tests`.

- [ ] Same procedure, in two commits if it helps review: (a) setup + plans, (b) sitting + review. Reminder lead labels → "Trước 1 giờ / Trước 1 ngày / Trước 3 ngày"; "Opens {time}" → "Mở lúc {time}"; "Sat — this plan has been fulfilled" → "Đã thi — lịch này đã hoàn thành"; "Left unanswered." → "Bỏ trống."; the countdown label; "Submit test" → "Nộp bài".

---

### Task 9: Analytics and the activity strip

**Files:** `app/dashboard/analytics/page.tsx`, `components/activity-strip.tsx`; namespace `analytics`.

- [ ] Same procedure. `weekdayInitial`/`weekdayLong` take the locale from `useLocale()`; the sr-only table headers too. "By notebook" → "Theo sổ tay"; "Not studied" → "Chưa ôn"; "Mock test" legend → "Thi thử"; the summary line via ICU plurals.

---

### Task 10: Close out

- [ ] `grep -rnE ">[^<>{}]*[A-Za-z]{4,}" app components --include='*.tsx' | grep -v "className\|import\|//"` — read every hit; anything user-facing left is a miss.
- [ ] Full manual pass in `vi`: sign in → every nav item → generate → study → quiz (typed) → plan a test → analytics → switch back to `en`. Reload each; no flash, no English leftovers.
- [ ] Spec status → `Implemented 2026-09-17`; note anything deliberately left English (e.g., the `(r)` key hint, "StudyFlow").
- [ ] Both suites, `tsc`, `pnpm lint` (0 errors). Offer merge via finishing-a-development-branch.
