"""Pasted text and fetched web pages as sources — the Django-free parts.

`is_public_url` is the guard that keeps the server from being talked into
fetching itself or anything on its network (a pasted link is user input);
`html_to_text` turns a page into the kind of text the generators expect;
`default_title` names a pasted block when the student did not.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from bs4 import BeautifulSoup

DEFAULT_PASTED_TITLE = "Pasted text"
MAX_TITLE = 80
_CHROME_TAGS = ("script", "style", "noscript", "nav", "header", "footer", "aside", "form", "iframe", "svg")
_INLINE_TAGS = ("a", "b", "i", "em", "strong", "span", "code", "u", "small", "sub", "sup", "mark", "abbr")


def _resolve(host: str) -> list[str]:
    """Every address the host resolves to. Patched in tests."""
    try:
        return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})
    except socket.gaierror:
        return []


def is_public_url(url: str) -> tuple[bool, str]:
    """(ok, reason). Only http(s) to a host whose *every* address is public.

    One private answer among several disqualifies the host: a name that
    resolves to a public address for the check and a private one for the
    fetch (DNS rebinding) must not get through on the first answer.
    """
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return False, "Only http and https links can be added."
    host = parsed.hostname
    if not host:
        return False, "That link has no host."
    addresses = _resolve(host)
    if not addresses:
        return False, "That host could not be found."
    for raw in addresses:
        addr = ipaddress.ip_address(raw)
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False, "Links to private or local addresses cannot be added."
    return True, ""


def html_to_text(html: str) -> tuple[str, str]:
    """(title, text) from a page, with scripts, styles and site chrome dropped.

    Blocks are joined with newlines so paragraph boundaries survive into the
    chunker, which splits on them.
    """
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for tag in soup(_CHROME_TAGS):
        tag.decompose()
    # Inline formatting is not a block boundary: "They release <b>oxygen</b>."
    # must come out as one line. Unwrap, then merge the now-adjacent strings.
    for tag in soup(_INLINE_TAGS):
        tag.unwrap()
    soup.smooth()
    root = soup.body or soup
    text = root.get_text("\n", strip=True)
    return title, text


def default_title(text: str) -> str:
    """The first non-empty line, cut to MAX_TITLE on a word boundary."""
    first = next((line.strip() for line in (text or "").splitlines() if line.strip()), "")
    if not first:
        return DEFAULT_PASTED_TITLE
    if len(first) <= MAX_TITLE:
        return first
    cut = first[: MAX_TITLE - 1].rsplit(" ", 1)[0].rstrip()
    return f"{cut}…"
