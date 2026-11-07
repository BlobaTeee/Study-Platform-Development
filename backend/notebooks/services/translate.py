"""A document's texts in the page language, translated on this machine.

The model (ml_pipeline/translator.py) runs locally, so reading in the other
language costs no AI requests. Each text is translated once and kept by
the hash of its words and the translator's version.
"""
import hashlib
import logging
import unicodedata

from ml_pipeline.language import detect_language
from ml_pipeline.translator import VERSION as TRANSLATOR_VERSION
from ml_pipeline.translator import translate as machine_translate

from ..models import Translation

logger = logging.getLogger(__name__)

LANGUAGES = ('vi', 'en')
MAX_TEXTS = 100
MAX_CHARS = 3000
# đ, and the marks under ă â ê ô ơ ư and the tones, once decomposed.
_VI_MARKS = set('đĐ\u0306\u0302\u031b\u0300\u0301\u0303\u0309\u0323')


def _hash(text: str) -> str:
    return hashlib.sha256(f'{TRANSLATOR_VERSION}\n{text}'.encode('utf-8')).hexdigest()


def _language(text: str) -> str:
    """'vi', 'en' or 'other'. A short label has too few words to tell, so
    its letters decide: Vietnamese marks mean Vietnamese, none mean English."""
    lang = detect_language(text)
    if lang in LANGUAGES or not any(c.isascii() and c.isalpha() for c in text):
        return lang
    marks = unicodedata.normalize('NFD', text)
    return 'vi' if any(c in _VI_MARKS for c in marks) else 'en'


def translate_texts(texts: list[str], target: str) -> tuple[list[str], bool]:
    """`texts` in `target`, in order, and whether the model was available.
    Without the model the originals come back, so the page still reads."""
    out = list(texts)
    todo: dict[str, list[int]] = {}             # source language → indexes to translate
    for i, text in enumerate(texts):
        if text.strip() and (lang := _language(text)) in LANGUAGES and lang != target:
            todo.setdefault(lang, []).append(i)
    if not todo:
        return out, True

    wanted = {_hash(texts[i]) for idx in todo.values() for i in idx}
    kept = dict(Translation.objects.filter(target=target, text_hash__in=wanted)
                .values_list('text_hash', 'translated'))
    for source, idx in todo.items():
        missing = list(dict.fromkeys(texts[i] for i in idx if _hash(texts[i]) not in kept))
        if missing:
            try:
                done = machine_translate(missing, source, target)
            except Exception as exc:  # noqa: BLE001 — model not installed or failed to load
                logger.info('Translation unavailable: %s', exc)
                return list(texts), False
            rows = [Translation(text_hash=_hash(t), target=target, translated=d) for t, d in zip(missing, done)]
            Translation.objects.bulk_create(rows, ignore_conflicts=True)
            kept.update((r.text_hash, r.translated) for r in rows)
        for i in idx:
            out[i] = kept[_hash(texts[i])]
    return out, True
