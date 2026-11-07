"""A document's texts in the page language, translated on this machine.

The model (ml_pipeline/translator.py) runs locally, so reading in the other
language costs no AI requests. Each text is translated once and kept by
the hash of its words and the translator's version. A short answer comes
with its question (its context): alone it is a word without a sense.
"""
import hashlib
import logging
import unicodedata

from ml_pipeline.language import detect_language
from ml_pipeline.translator import VERSION as TRANSLATOR_VERSION
from ml_pipeline.translator import translate as machine_translate
from ml_pipeline.translator import translate_in_context as machine_translate_in_context

from ..models import Translation

logger = logging.getLogger(__name__)

LANGUAGES = ('vi', 'en')
MAX_TEXTS = 100
MAX_CHARS = 3000
# đ, and the marks under ă â ê ô ơ ư and the tones, once decomposed.
_VI_MARKS = set('đĐ\u0306\u0302\u031b\u0300\u0301\u0303\u0309\u0323')


def _hash(text: str, context: str | None = None) -> str:
    key = f'{TRANSLATOR_VERSION}\n{text}' if context is None else f'{TRANSLATOR_VERSION}\n{context}\n{text}'
    return hashlib.sha256(key.encode('utf-8')).hexdigest()


def _language(text: str) -> str:
    """'vi', 'en' or 'other'. A short label has too few words to tell, so
    its letters decide: Vietnamese marks mean Vietnamese, none mean English."""
    lang = detect_language(text)
    if lang in LANGUAGES or not any(c.isascii() and c.isalpha() for c in text):
        return lang
    marks = unicodedata.normalize('NFD', text)
    return 'vi' if any(c in _VI_MARKS for c in marks) else 'en'


def _source(text: str, context: str | None) -> str:
    """The language `text` is in. A short answer's question has the words to tell."""
    if context is None:
        return _language(text)
    return _language(context) if any(c.isalpha() for c in text) else 'other'


def _translated(items: list[tuple[str, str | None]], source: str, target: str) -> list[str] | None:
    """Each (text, question or None) of `items` from `source` to `target`, from
    the kept translations or the model; None when the model is not available."""
    key = [_hash(t, c) for t, c in items]
    kept = dict(Translation.objects.filter(target=target, text_hash__in=set(key))
                .values_list('text_hash', 'translated'))
    for asked in (False, True):
        missing = list(dict.fromkeys(item for item, k in zip(items, key) if k not in kept and (item[1] is not None) == asked))
        if not missing:
            continue
        try:
            done = (machine_translate_in_context(missing, source, target) if asked
                    else machine_translate([t for t, _ in missing], source, target))
        except Exception as exc:  # noqa: BLE001 — model not installed or failed to load
            logger.info('Translation unavailable: %s', exc)
            return None
        rows = [Translation(text_hash=_hash(t, c), target=target, translated=d) for (t, c), d in zip(missing, done)]
        Translation.objects.bulk_create(rows, ignore_conflicts=True)
        kept.update((r.text_hash, r.translated) for r in rows)
    return [kept[k] for k in key]


def translate_texts(texts: list[str], target: str, contexts: list[str | None] | None = None) -> tuple[list[str], bool]:
    """`texts` in `target`, in order, and whether the model was available.
    `contexts[i]`, when given, is the question `texts[i]` answers. Without
    the model the originals come back, so the page still reads."""
    contexts = contexts or [None] * len(texts)
    out = list(texts)
    todo: dict[str, list[int]] = {}             # source language → indexes to translate
    for i, (text, context) in enumerate(zip(texts, contexts)):
        if text.strip() and (lang := _source(text, context)) in LANGUAGES and lang != target:
            todo.setdefault(lang, []).append(i)
    for source, idx in todo.items():
        done = _translated([(texts[i], contexts[i]) for i in idx], source, target)
        if done is None:
            return list(texts), False
        for i, d in zip(idx, done):
            out[i] = d
    return out, True


def into_language_of(text: str, context: str) -> str | None:
    """`text`, a typed answer, in the language of `context`, its question; None
    when it is in that language already or the model is not available."""
    target, source = _language(context), _language(text)
    if target not in LANGUAGES or source not in LANGUAGES or source == target or not text.strip():
        return None
    # The question in the answer's language: a prompt in two languages confuses
    # the model. The page has usually asked for it already, so it is kept.
    (question,), _ = translate_texts([context], source)
    done = _translated([(text, question)], source, target)
    return done[0] if done else None
