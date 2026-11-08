"""A document's texts in the page language, translated on this machine.

The model (ml_pipeline/translator.py) runs locally, so reading in the other
language costs no AI requests. Each text is translated once and kept by
the hash of its words and the translator's version. A short answer comes
with its question (its context): alone it is a word without a sense.
"""
import hashlib
import logging
import unicodedata
from dataclasses import dataclass, field

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


@dataclass
class Plan:
    """What a set of texts needs: the translations kept already, and what the
    model has to do, by (source language, asked with a question). Made and
    finished on the request's thread (they touch the database); the model's
    part, `run`, touches nothing else, so it can run on a thread of its own."""
    target: str
    texts: list[str]
    contexts: list[str | None]
    todo: dict[str, list[int]]                    # source language → indexes to translate
    kept: dict[str, str] = field(default_factory=dict)
    missing: dict[tuple[str, bool], list[tuple[str, str | None]]] = field(default_factory=dict)


def _plan(target: str, texts: list[str], contexts: list[str | None], todo: dict[str, list[int]]) -> Plan:
    plan = Plan(target, texts, contexts, todo)
    keys = {_hash(texts[i], contexts[i]) for idx in todo.values() for i in idx}
    plan.kept = dict(Translation.objects.filter(target=target, text_hash__in=keys)
                     .values_list('text_hash', 'translated'))
    for source, idx in todo.items():
        for item in dict.fromkeys((texts[i], contexts[i]) for i in idx):
            if _hash(*item) not in plan.kept:
                plan.missing.setdefault((source, item[1] is not None), []).append(item)
    return plan


def plan_texts(texts: list[str], target: str, contexts: list[str | None] | None = None) -> Plan:
    """The plan for `texts` in `target`; `contexts[i]`, when given, is the
    question `texts[i]` answers."""
    contexts = contexts or [None] * len(texts)
    todo: dict[str, list[int]] = {}
    for i, (text, context) in enumerate(zip(texts, contexts)):
        if text.strip() and (lang := _source(text, context)) in LANGUAGES and lang != target:
            todo.setdefault(lang, []).append(i)
    return _plan(target, texts, contexts, todo)


def run(plan: Plan) -> dict | None:
    """The model's translations of what `plan` is missing, or None when the
    model is not available. No database here."""
    done = {}
    for (source, asked), items in plan.missing.items():
        try:
            done[(source, asked)] = (machine_translate_in_context(items, source, plan.target) if asked
                                     else machine_translate([t for t, _ in items], source, plan.target))
        except Exception as exc:  # noqa: BLE001 — model not installed or failed to load
            logger.info('Translation unavailable: %s', exc)
            return None
    return done


def finish(plan: Plan, done: dict | None) -> tuple[list[str], bool]:
    """`plan`'s texts in its language, keeping what the model did; the
    originals, and False, when it could not."""
    if done is None:
        return list(plan.texts), False
    rows = [Translation(text_hash=_hash(t, c), target=plan.target, translated=d)
            for key, items in plan.missing.items() for (t, c), d in zip(items, done[key])]
    Translation.objects.bulk_create(rows, ignore_conflicts=True)
    plan.kept.update((r.text_hash, r.translated) for r in rows)
    out = list(plan.texts)
    for idx in plan.todo.values():
        for i in idx:
            out[i] = plan.kept[_hash(plan.texts[i], plan.contexts[i])]
    return out, True


def translate_texts(texts: list[str], target: str, contexts: list[str | None] | None = None) -> tuple[list[str], bool]:
    """`texts` in `target`, in order, and whether the model was available.
    Without the model the originals come back, so the page still reads."""
    plan = plan_texts(texts, target, contexts)
    return finish(plan, run(plan))


def into_language_of(text: str, context: str) -> str | None:
    """`text`, a typed answer, in the language of `context`, its question; None
    when it is in that language already or the model is not available."""
    target, source = _language(context), _language(text)
    if target not in LANGUAGES or source not in LANGUAGES or source == target or not text.strip():
        return None
    # The question in the answer's language: a prompt in two languages confuses
    # the model. The page has usually asked for it already, so it is kept.
    (question,), _ = translate_texts([context], source)
    plan = _plan(target, [text], [question], {source: [0]})
    (done,), translated = finish(plan, run(plan))
    return done if translated else None
