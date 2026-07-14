"""Shared content extraction for the generation services (classical, local).

spaCy for sentence segmentation + key terms; TF-IDF for sentence salience.
Framework-free; no LLM/network.
"""
from __future__ import annotations

import re
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

# Light/filler nouns that make poor cloze answers ("takes ___ place" -> "place").
# Matched on the noun-chunk root lemma, so plurals are covered. Used only to
# *deprioritize*: a light noun is still chosen if it's the sole option.
LIGHT_NOUNS = frozenset({
    "place", "part", "kind", "sort", "type", "way", "thing", "number",
    "amount", "case", "example", "fact", "point", "side", "use", "result",
    "means", "variety", "range", "lot", "bit", "piece", "area", "member",
    "name", "form",
})

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


def blank_term(sentence: str, term: str, blank: str) -> str:
    """Replace *every* standalone occurrence of `term` with `blank`.

    Blanks all occurrences so a term that repeats in its sentence is never left
    visible in the stem (which would leak the answer and let the scorer trivially
    pass the question). Word-boundary aware, so a term like "cell" is not blanked
    inside "cellular". Falls back to a plain replace when no boundaried match
    exists (e.g. terms with leading/trailing non-word chars).
    """
    replaced = re.sub(rf"\b{re.escape(term)}\b", blank, sentence)
    return replaced if replaced != sentence else sentence.replace(term, blank)


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
        (leading determiner stripped), skipping chunks whose text can't be
        matched back to the sentence (e.g. spacing around clitics)."""
        for ent in sent.ents:
            if ent.label_ in ANSWERABLE_ENT_LABELS and ent.text.strip():
                return ent.text.strip(), ent.label_
        best, best_w = None, -1.0
        fallback, fallback_w = None, -1.0  # light-noun fallback (used only if no better term)
        for chunk in sent.noun_chunks:
            root = chunk.root
            if root.is_stop or root.pos_ == "PRON":
                continue
            # Strip a leading determiner, then slice the ORIGINAL text so spacing
            # around clitics (possessive "'s") is preserved.
            start = chunk[1] if (len(chunk) > 1 and chunk[0].pos_ == "DET") else chunk[0]
            phrase = sent.doc.text[start.idx:chunk[-1].idx + len(chunk[-1].text)].strip()
            if not phrase or phrase not in sent.text:
                continue
            w = idf[vocab[root.text.lower()]] if root.text.lower() in vocab else 0.0
            if root.lemma_.lower() in LIGHT_NOUNS:
                if w > fallback_w:
                    fallback, fallback_w = phrase, w
                continue
            if w > best_w:
                best, best_w = phrase, w
        chosen = best if best is not None else fallback
        return (chosen, NOUN_CHUNK_LABEL) if chosen else None
