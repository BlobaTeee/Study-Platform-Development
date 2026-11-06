"""English ↔ Vietnamese translation on this machine (notebook 12).

The model was chosen on the IWSLT'15 test set and on the app's own key
points (notebook 12). It loads on first use and stays loaded; torch and
transformers are imported only then, so the rest of the pipeline does not
need them. Django-free.
"""
from __future__ import annotations

import re
import threading

#: One model for both directions (VietAI, trained on the MTet and PhoMT
#: English–Vietnamese collections; licence OpenRAIL). It reads "en: …" or "vi: …" and writes the other
#: language with its own prefix. Helsinki-NLP/opus-mt-en-vi was measured too
#: and loops on short labels ("cấu cấu cấu …"), see notebook 12.
MODEL = "VietAI/envit5-translation"
BATCH = 16
#: Greedy: the same BLEU as 4 beams on IWSLT'15 (35.4), four times as fast.
BEAMS = 1

_loaded: list = []
_lock = threading.Lock()
# A sentence ends at . ! ? followed by a space and a capital or a digit.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ỹ0-9\"'(])")


def _model():
    if not _loaded:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        tokenizer = AutoTokenizer.from_pretrained(MODEL)
        model = AutoModelForSeq2SeqLM.from_pretrained(MODEL).to(device).eval()
        _loaded.extend([tokenizer, model, device])
    return _loaded


def split_sentences(text: str) -> list[str]:
    """`text` as sentences: a model trained on sentences translates a
    paragraph best one sentence at a time."""
    return [s for s in _SENTENCE_END.split(text.strip()) if s]


def translate(texts: list[str], source: str, target: str) -> list[str]:
    """Each of `texts` from `source` to `target` ('en' or 'vi'), in order."""
    import torch

    pieces = [split_sentences(t) for t in texts]
    flat = [s for p in pieces for s in p]
    out: list[str] = []
    with _lock:                                  # one generate at a time on the device
        tokenizer, model, device = _model()
        for i in range(0, len(flat), BATCH):
            batch = tokenizer([f"{source}: {s}" for s in flat[i:i + BATCH]], return_tensors="pt", padding=True,
                              truncation=True, max_length=256).to(device)
            with torch.no_grad():
                generated = model.generate(**batch, num_beams=BEAMS, max_new_tokens=256)
            out += [o.removeprefix(f"{target}:").strip() for o in tokenizer.batch_decode(generated, skip_special_tokens=True)]
    joined, at = [], 0
    for p in pieces:
        joined.append(" ".join(out[at:at + len(p)]))
        at += len(p)
    return joined
