"""One name per idea, written natively in each language.

The interface once called the same thing a "source" on one page and a
"document" on the next, and left English words ("notebook", "quiz") in
the Vietnamese. These are the words each side must not use; the word to
use instead is in the message.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "messages"
ARGUMENT = re.compile(r"\{\w+\}")             # `{notebook}` names an argument, not a word

AVOID = {
    "en": {
        r"\bsources?\b": 'call it a "document"',
        r"\bmain ideas?\b": 'call them "key points"',
        r"\bshaky\b": 'say "not solid yet"',
        r"\bmistake bank\b": 'say "mistakes to redo"',
    },
    "vi": {
        r"\bnotebooks?\b": 'viết "sổ tay"',
        r"\bquiz(zes)?\b": 'viết "bài kiểm tra"',
        r"ngân hàng lỗi sai": 'viết "câu sai cần làm lại"',
    },
}


def _strings(d, prefix=""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _strings(v, f"{prefix}{k}.")
        else:
            yield f"{prefix}{k}", v


def _breaches(lang):
    messages = json.loads((ROOT / f"{lang}.json").read_text())
    out = []
    for key, text in _strings(messages):
        plain = ARGUMENT.sub("", text)
        out += [f"{key}: {text!r} ({fix})" for pattern, fix in AVOID[lang].items()
                if re.search(pattern, plain, re.IGNORECASE)]
    return out


def test_english_uses_one_name_per_idea():
    assert _breaches("en") == []


def test_vietnamese_has_no_english_names_left():
    assert _breaches("vi") == []
