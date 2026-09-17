"""Which language a source is written in — Vietnamese, English, or other.

Two cheap signals, no models: letters that only Vietnamese uses (ă â đ ê ô ơ ư
and the tone marks), and the function words each language cannot write a
sentence without. Diacritics alone miss Vietnamese typed without tone marks;
words alone miss short technical text; together they cover what the app
sees. Django-free, so the notebook and the pure tests can use it.
"""
from __future__ import annotations

import re
import unicodedata

_VI_LETTERS = set("ăâđêôơưĂÂĐÊÔƠƯ")
_VI_TONES = {"̀", "́", "̃", "̉", "̣"}  # grave, acute, tilde, hook, dot below
_VI_WORDS = {"và", "của", "là", "không", "được", "trong", "có", "những", "các", "với", "cho",
             "này", "một", "để", "khi", "người", "về", "từ", "như", "cũng", "đã", "sẽ", "bị",
             # the same words as typed without tone marks
             "va", "cua", "la", "khong", "duoc", "trong", "co", "nhung", "cac", "voi", "cho",
             "nay", "mot", "de", "khi", "nguoi", "ve", "tu", "nhu", "cung", "da", "se", "bi",
             "ban", "can", "hoc", "bai", "lam", "minh"}
_EN_WORDS = {"the", "and", "of", "to", "in", "is", "are", "that", "for", "with", "as", "by",
             "on", "this", "which", "from", "was", "be", "an", "or", "it", "at", "not"}
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def detect_language(text: str) -> str:
    """'vi', 'en', or 'other' for `text`."""
    words = [w.lower() for w in _WORD.findall(text or "")]
    if not words:
        return "other"
    letters = [c for c in text if c.isalpha()]
    latin = sum(1 for c in letters if "LATIN" in unicodedata.name(c, ""))
    if letters and latin / len(letters) < 0.5:
        return "other"
    decomposed = unicodedata.normalize("NFD", text)
    diacritic_hits = sum(1 for c in text if c in _VI_LETTERS) + sum(1 for c in decomposed if c in _VI_TONES)
    vi_score = sum(1 for w in words if w in _VI_WORDS) + diacritic_hits / 3
    en_score = sum(1 for w in words if w in _EN_WORDS)
    if vi_score == 0 and en_score == 0:
        return "other"
    return "vi" if vi_score > en_score else "en"


def language_name(code: str) -> str:
    """How the generation prompt names the language to write in."""
    return {"vi": "Vietnamese", "en": "English"}.get(code, "the same language as the excerpt")
