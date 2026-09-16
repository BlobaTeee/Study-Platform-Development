"""The two message catalogues describe the same interface.

A key present on one side only renders as its own path in the other
language; a placeholder present on one side only breaks formatting. Both
are caught here rather than by a Vietnamese-speaking user.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "messages"
# Messages that are legitimately the same in both languages: proper nouns,
# loanwords, and format names.
IDENTICAL_OK = {"StudyFlow", "English", "Email", "PDF · Word (.docx) · PowerPoint (.pptx)", "PDF · DOCX · PPTX"}
# An ICU argument is `{name}` or `{name, plural, …}`; the text inside a plural
# branch (`{# cards}`) is not one, so the name must be followed by `,` or `}`.
PLACEHOLDER = re.compile(r"\{(\w+)\s*[,}]")


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


PRINTED = re.compile(r"\{(\w+)\s*\}")


def _without_plural_blocks(msg):
    """`msg` with every `{name, plural, …}` block removed (braces balanced),
    so the words inside a branch (`one {review}`) are not read as placeholders."""
    out, i = [], 0
    while i < len(msg):
        m = re.compile(r"\{\w+\s*,\s*plural").search(msg, i)
        if not m:
            out.append(msg[i:]); break
        out.append(msg[i:m.start()])
        depth, j = 0, m.start()
        while j < len(msg):
            depth += msg[j] == "{"
            depth -= msg[j] == "}"
            j += 1
            if depth == 0: break
        i = j
    return "".join(out)


def test_placeholders_match():
    """Every value the English message prints, the Vietnamese one prints too;
    the Vietnamese one names nothing English does not pass. A plural
    *selector* (`{count, plural, …}` where the number itself is shown
    elsewhere) may be dropped: Vietnamese has no plural to select."""
    en, vi = _load("en"), _load("vi")
    for key in en:
        en_all, vi_all = set(PLACEHOLDER.findall(en[key])), set(PLACEHOLDER.findall(vi[key]))
        stripped = _without_plural_blocks(en[key])
        # `#` inside a plural block prints the count; outside one it is just a hash.
        count_printed = "#" in en[key] and "#" not in stripped
        en_printed = set(PRINTED.findall(stripped)) | ({"count"} if count_printed else set())
        assert vi_all <= en_all, f"{key}: vi names {vi_all - en_all} which en does not pass"
        assert en_printed <= vi_all, f"{key}: vi drops printed {en_printed - vi_all}"


def test_no_message_is_left_empty_or_untranslated():
    en, vi = _load("en"), _load("vi")
    for key in en:
        assert en[key].strip() and vi[key].strip(), key
        # A Vietnamese message identical to the English one is allowed only
        # for proper nouns, loanwords and symbols (StudyFlow, Email, EN, ·).
        if vi[key] == en[key]:
            assert (not re.search(r"[a-z]{4,}", en[key])
                    or en[key] in IDENTICAL_OK), key
