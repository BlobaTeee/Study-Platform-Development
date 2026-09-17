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


def fetch_page(url: str) -> tuple[str, str]:
    """(title, text) of the page at `url`."""
    ok, why = is_public_url(url)
    if not ok:
        raise PageFetchError(_(why))
    try:
        resp = requests.get(url, timeout=TIMEOUT_SECONDS, stream=True,
                            headers={'User-Agent': USER_AGENT}, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise PageFetchError(_('Could not fetch that link (%(why)s).') % {'why': exc.__class__.__name__}) from exc
    except Exception as exc:  # raise_for_status on a stub, odd transports
        raise PageFetchError(_('Could not fetch that link.')) from exc

    ctype = (resp.headers.get('Content-Type') or '').lower()
    if 'html' not in ctype and 'xml' not in ctype:
        raise PageFetchError(_('That link is not a web page. Upload the file instead.'))

    body = resp.content
    if len(body) > MAX_BYTES:
        raise PageFetchError(_('That page is too large to import.'))

    title, text = html_to_text(body.decode(getattr(resp, 'encoding', None) or 'utf-8', errors='replace'))
    if not text.strip():
        raise PageFetchError(_('No readable text was found on that page.'))
    return title, text
