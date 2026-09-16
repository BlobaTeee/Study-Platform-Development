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
        # for proper nouns, loanwords and symbols (StudyFlow, Email, EN, ·).
        if vi[key] == en[key]:
            assert not re.search(r"[a-z]{4,}", en[key]) or en[key] in ("StudyFlow", "English", "Email"), key
