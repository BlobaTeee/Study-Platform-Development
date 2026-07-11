"""Shared content extraction for the generation services (classical, local).

spaCy for sentence segmentation + key terms; TF-IDF for sentence salience.
Framework-free; no LLM/network.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import textstat
from sklearn.feature_extraction.text import TfidfVectorizer

# Nominal entities that read well as "What is {term}?" definitional cards.
DEFINITIONAL_LABELS = {
    "PERSON", "ORG", "GPE", "LOC", "NORP", "FAC", "EVENT",
    "WORK_OF_ART", "PRODUCT", "LAW", "LANGUAGE",
}
# Numeric/temporal entities that read better as cloze.
NUMERIC_LABELS = {"DATE", "TIME", "PERCENT", "MONEY", "QUANTITY", "ORDINAL", "CARDINAL"}
ANSWERABLE_ENT_LABELS = DEFINITIONAL_LABELS | NUMERIC_LABELS
NOUN_CHUNK_LABEL = "NOUN_CHUNK"

MIN_SENT_TOKENS = 5
MAX_SENT_TOKENS = 40
MAX_TEXT_CHARS = 100_000

# Difficulty thresholds on Flesch reading-ease (higher = easier to read).
EASY_READING_EASE = 60.0
HARD_READING_EASE = 30.0


@dataclass(frozen=True)
class Candidate:
    sentence: str
    term: str
    label: str
    score: float


@lru_cache(maxsize=1)
def get_nlp():
    """Memoized spaCy pipeline. Raises if en_core_web_sm is unavailable."""
    import spacy
    return spacy.load("en_core_web_sm")


def difficulty_for(candidate: "Candidate") -> str:
    """Bucket difficulty from the support sentence's reading ease."""
    text = candidate.sentence or ""
    if not text.strip():
        return "medium"
    ease = textstat.flesch_reading_ease(text)
    if ease >= EASY_READING_EASE:
        return "easy"
    if ease <= HARD_READING_EASE:
        return "hard"
    return "medium"


class ContentExtractor:
    def __init__(self, nlp=None):
        self._nlp = nlp

    @property
    def nlp(self):
        return self._nlp if self._nlp is not None else get_nlp()

    def extract_candidates(self, text: str, max_candidates: int) -> list[Candidate]:
        text = (text or "")[:MAX_TEXT_CHARS].strip()
        if not text or max_candidates <= 0:
            return []
        doc = self.nlp(text)
        sents = [s for s in doc.sents
                 if MIN_SENT_TOKENS <= sum(1 for t in s if not t.is_space) <= MAX_SENT_TOKENS]
        if not sents:
            return []

        sent_texts = [s.text.strip() for s in sents]
        try:
            vec = TfidfVectorizer(stop_words="english")
            matrix = vec.fit_transform(sent_texts)
        except ValueError:
            return []  # empty vocabulary (all stopwords)
        salience = np.asarray(matrix.sum(axis=1)).ravel()
        idf, vocab = vec.idf_, vec.vocabulary_

        order = sorted(range(len(sents)), key=lambda i: (-salience[i], sent_texts[i]))
        out, seen = [], set()
        for i in order:
            picked = self._pick_term(sents[i], idf, vocab)
            if picked is None:
                continue
            term, label = picked
            key = term.lower()
            if key in seen or term not in sent_texts[i]:
                continue
            seen.add(key)
            out.append(Candidate(sentence=sent_texts[i], term=term, label=label,
                                 score=float(salience[i])))
            if len(out) >= max_candidates:
                break
        return out

    @staticmethod
    def _pick_term(sent, idf, vocab):
        """Prefer an answerable named entity; else the highest-IDF noun chunk
        (determiners stripped)."""
        for ent in sent.ents:
            if ent.label_ in ANSWERABLE_ENT_LABELS and ent.text.strip():
                return ent.text.strip(), ent.label_
        best, best_w = None, -1.0
        for chunk in sent.noun_chunks:
            root = chunk.root
            if root.is_stop or root.pos_ == "PRON":
                continue
            phrase = " ".join(t.text for t in chunk if t.pos_ != "DET").strip()
            if not phrase:
                continue
            w = idf[vocab[root.text.lower()]] if root.text.lower() in vocab else 0.0
            if w > best_w:
                best, best_w = phrase, w
        return (best, NOUN_CHUNK_LABEL) if best else None
