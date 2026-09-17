"""Fetch a web page the student pasted a link to, safely.

The guard (`web_source.is_public_url`) runs before any connection; the
fetch itself is bounded in time and size and accepts only HTML. Everything
that can go wrong raises `PageFetchError` with a sentence for the student.
"""
from __future__ import annotations

import requests
from django.utils.translation import gettext as _, gettext_noop

from .web_source import html_to_text, is_public_url

TIMEOUT_SECONDS = 10
MAX_BYTES = 5 * 1024 * 1024
USER_AGENT = 'StudyFlow/1.0 (+study notes importer)'


# The guard's reasons live in web_source (Django-free); listing them here lets
# makemessages pick them up, and `_(why)` above translates whichever fires.
_GUARD_REASONS = (
    gettext_noop('Only http and https links can be added.'),
    gettext_noop('That link has no host.'),
    gettext_noop('That host could not be found.'),
    gettext_noop('Links to private or local addresses cannot be added.'),
)


class PageFetchError(ValueError):
    """The link could not be turned into a source; `str(exc)` is user-facing."""


class FetchedPage:
    """What a link resolved to: an HTML page (title + text) or a PDF (bytes)."""
    def __init__(self, kind: str, title: str = '', text: str = '', pdf: bytes = b''):
        self.kind, self.title, self.text, self.pdf = kind, title, text, pdf


def fetch_page(url: str) -> FetchedPage:
    ok, why = is_public_url(url)
    if not ok:
        raise PageFetchError(_(why))
    try:
        resp = requests.get(url, timeout=TIMEOUT_SECONDS, stream=True,
                            headers={'User-Agent': USER_AGENT}, allow_redirects=True)
    except requests.RequestException as exc:
        raise PageFetchError(_('Could not fetch that link (%(why)s).') % {'why': exc.__class__.__name__}) from exc

    status = getattr(resp, 'status_code', 200)
    if status in (401, 403, 429, 503):
        # Publishers (ACM, Elsevier, …) sit behind a bot challenge or a
        # paywall. Nothing here can, or should, get past that; the student
        # can save the file in their browser and upload it.
        raise PageFetchError(_('That site blocks automated access. Download the file in your '
                               'browser and upload it here instead.'))
    if status >= 400:
        raise PageFetchError(_('Could not fetch that link (HTTP %(status)s).') % {'status': status})

    body = resp.content
    if len(body) > MAX_BYTES:
        raise PageFetchError(_('That page is too large to import.'))

    ctype = (resp.headers.get('Content-Type') or '').lower()
    if 'pdf' in ctype or body[:5] == b'%PDF-':
        return FetchedPage('pdf', pdf=body)
    if 'html' not in ctype and 'xml' not in ctype:
        raise PageFetchError(_('That link is not a web page or a PDF. Upload the file instead.'))

    title, text = html_to_text(body.decode(getattr(resp, 'encoding', None) or 'utf-8', errors='replace'))
    if not text.strip():
        raise PageFetchError(_('No readable text was found on that page.'))
    return FetchedPage('html', title=title, text=text)
