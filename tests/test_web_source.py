"""Pasted text and fetched pages as sources: the pure parts."""
import importlib.util
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "notebooks" / "services" / "web_source.py")


def _load():
    spec = importlib.util.spec_from_file_location("web_source_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ws = _load()


# ---- is_public_url: the server must never be talked into fetching itself ----

def test_public_http_and_https_urls_are_allowed(monkeypatch):
    monkeypatch.setattr(ws, "_resolve", lambda host: ["93.184.216.34"])
    assert ws.is_public_url("https://example.com/notes") == (True, "")
    assert ws.is_public_url("http://example.com/notes") == (True, "")


def test_other_schemes_are_refused():
    ok, why = ws.is_public_url("ftp://example.com/x")
    assert ok is False and "http" in why
    assert ws.is_public_url("file:///etc/passwd")[0] is False
    assert ws.is_public_url("javascript:alert(1)")[0] is False


def test_private_loopback_and_link_local_hosts_are_refused(monkeypatch):
    cases = {
        "http://localhost/": ["127.0.0.1"],
        "http://127.0.0.1:8000/admin/": ["127.0.0.1"],
        "http://10.0.0.5/": ["10.0.0.5"],
        "http://192.168.1.1/": ["192.168.1.1"],
        "http://169.254.169.254/latest/meta-data": ["169.254.169.254"],
        "http://[::1]/": ["::1"],
        "http://internal.corp/": ["172.16.0.9"],
    }
    for url, addrs in cases.items():
        monkeypatch.setattr(ws, "_resolve", lambda host, a=addrs: a)
        ok, why = ws.is_public_url(url)
        assert ok is False, url
        assert "private" in why or "local" in why


def test_a_host_that_does_not_resolve_is_refused(monkeypatch):
    monkeypatch.setattr(ws, "_resolve", lambda host: [])
    assert ws.is_public_url("https://no-such-host.invalid/")[0] is False


def test_a_host_with_one_private_address_among_public_ones_is_refused(monkeypatch):
    # DNS rebinding-style: any private answer disqualifies the host.
    monkeypatch.setattr(ws, "_resolve", lambda host: ["93.184.216.34", "10.0.0.1"])
    assert ws.is_public_url("https://tricky.example/")[0] is False


# ---- html_to_text ---------------------------------------------------------------

HTML = """<html><head><title> Photosynthesis — Notes </title>
<style>p{color:red}</style><script>alert(1)</script></head>
<body><nav>Home · About</nav><header>Site header</header>
<main><h1>Photosynthesis</h1><p>Plants absorb carbon dioxide.</p>
<p>They release <b>oxygen</b>.</p></main>
<footer>© 2026</footer></body></html>"""


def test_html_to_text_keeps_content_and_drops_chrome():
    title, text = ws.html_to_text(HTML)
    assert title == "Photosynthesis — Notes"
    assert "Plants absorb carbon dioxide." in text
    assert "They release oxygen." in text
    for chrome in ("alert(1)", "color:red", "Home · About", "Site header", "© 2026"):
        assert chrome not in text


def test_html_to_text_separates_blocks_with_newlines():
    _, text = ws.html_to_text(HTML)
    assert "Photosynthesis\n" in text
    assert "carbon dioxide.\n" in text


def test_html_without_a_title_yields_an_empty_title():
    title, text = ws.html_to_text("<p>Just a paragraph.</p>")
    assert title == "" and text.strip() == "Just a paragraph."


# ---- default_title ----------------------------------------------------------------

def test_default_title_is_the_first_line_trimmed():
    assert ws.default_title("  Chapter 3: Cells\n\nCells are…") == "Chapter 3: Cells"


def test_default_title_is_cut_to_eighty_characters_on_a_word():
    long = "word " * 40
    title = ws.default_title(long)
    assert len(title) <= 80 and not title.endswith(" ") and title.endswith("…")


def test_default_title_for_empty_text():
    assert ws.default_title("   ") == "Pasted text"
