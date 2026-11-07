"""English ↔ Vietnamese translation on this machine (notebook 12).

The model was chosen on the IWSLT'15 test set and on the app's own key
points (notebook 12). It loads on first use and stays loaded; torch and
transformers are imported only then, so the rest of the pipeline does not
need them. Django-free.
"""
from __future__ import annotations

import re
import threading
import unicodedata
from functools import lru_cache

#: One model for both directions (VietAI, trained on the MTet and PhoMT
#: English–Vietnamese collections; licence OpenRAIL). It reads "en: …" or "vi: …" and writes the other
#: language with its own prefix. Helsinki-NLP/opus-mt-en-vi was measured too
#: and loops on short labels ("cấu cấu cấu …"), see notebook 12.
MODEL = "VietAI/envit5-translation"
BATCH = 16
#: Greedy: the same BLEU as 4 beams on IWSLT'15 (35.4), four times as fast.
BEAMS = 1
#: Raised whenever the output changes, so translations kept from before are made again.
VERSION = 2

_loaded: list = []
_lock = threading.Lock()
# A sentence ends at . ! ? followed by a space and a capital or a digit.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ỹ0-9\"'(])")
_BLANK = re.compile(r"_{2,}")
#: How a short answer is asked with its question, and the words the model
#: writes before the answer in each language (notebook 12, section 6).
_ANSWER_LEAD = {"en": "Answer:", "vi": "Đáp án:"}
_ANSWER_WORDS = {
    "en": re.compile(r"(?:the answer is|answer:)", re.I),
    "vi": re.compile(r"(?:đáp án:|câu trả lời là|câu trả lời:|trả lời:|đáp:)", re.I),
}


def _model():
    if not _loaded:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        tokenizer = AutoTokenizer.from_pretrained(MODEL)
        model = AutoModelForSeq2SeqLM.from_pretrained(MODEL).to(device).eval()
        _loaded.extend([tokenizer, model, device, _known(tokenizer)])
    return _loaded


def _known(tokenizer):
    @lru_cache(maxsize=None)
    def known(c: str) -> bool:
        ids = tokenizer(c, add_special_tokens=False).input_ids
        return bool(ids) and tokenizer.unk_token_id not in ids
    return known


def split_sentences(text: str) -> list[str]:
    """`text` as sentences: a model trained on sentences translates a
    paragraph best one sentence at a time."""
    return [s for s in _SENTENCE_END.split(text.strip()) if s]


def as_sentence_case(text: str) -> str:
    """A name written in Title Case, in sentence case: the model reads Title
    Case like a menu item and gets it wrong ("Nutrient Cycles" → "Công thức
    tính toán", notebook 12). Acronyms and mixed-case words stay as written."""
    words = text.split()
    long = [w for w in words if w[0].isalpha() and sum(c.isalpha() for c in w) >= 4]
    if re.search(r"[.!?]$", text.strip()) or len(long) < 2 or not all(w[0].isupper() for w in long):
        return text
    lower = [w.lower() if len(w) > 1 and w[0].isupper() and w[1:] == w[1:].lower() else w for w in words[1:]]
    return " ".join(words[:1] + lower)


def first_letter_as_in(source: str, translated: str) -> str:
    """`translated` starting with a capital when `source` does."""
    a = next((c for c in source if c.isalpha()), "")
    i = next((i for i, c in enumerate(translated) if c.isalpha()), None)
    if i is None or not a.isupper():
        return translated
    return translated[:i] + translated[i].upper() + translated[i + 1:]


def shield(sentence: str, known) -> tuple[str, list[str]]:
    """`sentence` with each run of characters the model cannot read (λ ≤ → °
    ø …, and super- and subscripts, which it reads as plain digits) replaced
    by <0>, <1>, …, and those runs in order. A word holding such a letter
    goes whole ("Brønsted-Lowry", "Δv"): with only the letter replaced the
    model garbles the rest. `known(c)` says whether the model has `c`."""
    odd = [not c.isspace() and (not known(c) or unicodedata.normalize("NFKC", c) != c) for c in sentence]
    for blank in _BLANK.finditer(sentence):       # the model drops a fill-in blank
        odd[blank.start():blank.end()] = [True] * (blank.end() - blank.start())
    for i, c in enumerate(sentence):
        if odd[i] and c.isalpha():
            for step in (-1, 1):
                j = i + step
                while 0 <= j < len(sentence) and (sentence[j].isalnum() or sentence[j] in "-'’"):
                    odd[j] = True
                    j += step
    spans: list[str] = []
    out: list[str] = []
    for i, c in enumerate(sentence):
        if not odd[i]:
            out.append(c)
        elif i and odd[i - 1]:
            spans[-1] += c
        else:
            out.append(f"<{len(spans)}>")
            spans.append(c)
    return "".join(out), spans


def unshield(translated: str, spans: list[str]) -> str | None:
    """The placeholders in `translated` put back, or None when the model lost
    or repeated one (the sentence is then better left as written)."""
    for i, span in enumerate(spans):
        if translated.count(f"<{i}>") != 1:
            return None
        translated = translated.replace(f"<{i}>", span)
    return translated


def answer_prompt(text: str, context: str, source: str) -> str:
    """`text`, a short answer, asked as the answer to `context`, its question:
    alone it is a word without a sense ("Force" → "Buộc")."""
    return f"{context} {_ANSWER_LEAD[source]} {text}."


def answer_from(translated: str, target: str) -> str | None:
    """The answer in a translated `answer_prompt`, or None when the model did
    not write it after an answer word."""
    found = list(_ANSWER_WORDS[target].finditer(translated))
    if not found:
        return None
    answer = translated[found[-1].end():].strip().rstrip(".").strip()
    return answer or None


def _generate(sentences: list[str], source: str, target: str) -> list[str]:
    """Each of `sentences`, prepared for the model, translated and put back."""
    import torch

    out: list[str] = []
    with _lock:                                  # one generate at a time on the device
        tokenizer, model, device, known = _model()
        shielded = [shield(as_sentence_case(s), known) for s in sentences]
        for i in range(0, len(sentences), BATCH):
            batch = tokenizer([f"{source}: {t}" for t, _ in shielded[i:i + BATCH]], return_tensors="pt",
                              padding=True, truncation=True, max_length=256).to(device)
            with torch.no_grad():
                generated = model.generate(**batch, num_beams=BEAMS, max_new_tokens=256)
            out += [o.removeprefix(f"{target}:").strip() for o in tokenizer.batch_decode(generated, skip_special_tokens=True)]
    for i, (s, (_, spans)) in enumerate(zip(sentences, shielded)):
        restored = unshield(out[i], spans)
        out[i] = s if restored is None else first_letter_as_in(s, restored)
    return out


def translate(texts: list[str], source: str, target: str) -> list[str]:
    """Each of `texts` from `source` to `target` ('en' or 'vi'), in order."""
    pieces = [split_sentences(t) for t in texts]
    out = _generate([s for p in pieces for s in p], source, target)
    joined, at = [], 0
    for p in pieces:
        joined.append(" ".join(out[at:at + len(p)]))
        at += len(p)
    return joined


def translate_in_context(pairs: list[tuple[str, str]], source: str, target: str) -> list[str]:
    """Each short answer of `pairs` (answer, its question) translated as the
    answer to its question; one the model does not mark as the answer is
    translated alone."""
    done = _generate([answer_prompt(text, context, source) for text, context in pairs], source, target)
    answers = [answer_from(d, target) for d in done]
    alone = [text for (text, _), a in zip(pairs, answers) if a is None]
    alone_done = iter(translate(alone, source, target) if alone else [])
    return [first_letter_as_in(text, a) if a is not None else next(alone_done) for (text, _), a in zip(pairs, answers)]
