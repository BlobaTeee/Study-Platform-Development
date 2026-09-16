"""Grading a typed answer against a reference: cheap rules first, the scorer last.

Rules, in order — the first that decides wins:
  1. exact after normalisation          -> correct
  2. near-string (plural, order, hyphen) -> correct
  2b. equals a distractor               -> wrong
  2c. reference longer than the scorer   -> near   (the LLM tier's case)
      was trained on
  3. AnswerScorer ranking                -> correct / near / wrong
An LLM tie-break for `near` lives in the Django layer (quizzes/services/
typed_grading.py); this module stays importable without Django so the
notebook and the pure tests can drive it.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

# Thresholds set from ml_pipeline/notebooks/04_short_answer_grading.ipynb —
# see reports/short_answer_metrics.json["chosen"]. tests/test_short_answer.py
# asserts these equal the report, so change both together.
T_STRING = 0.8   # notebook 04, SciQ test (2,722 pos / 3,533 neg): cascade precision
T_RATIO = 0.6    # 0.985 / recall 0.994 with support; 0.994 / 0.964 without.

# The scorer was trained on SciQ, whose answers are one to three words. On a
# sentence-length reference its probabilities are meaningless — it gave a
# 14-word reference 0.012 and an unrelated typed answer 0.023 — so past this
# length the scorer is not consulted and the case goes to the LLM tier.
MAX_SCORER_REFERENCE_WORDS = 4

_LEADING_ARTICLE = re.compile(r"^(a|an|the)\s+")
_NON_WORD = re.compile(r"[^\w\s]")


def normalise(text: str) -> str:
    """Lowercase, no punctuation, single spaces, no leading article."""
    text = _NON_WORD.sub(" ", text.lower())
    text = re.sub(r"\s+", " ", text).strip()
    return _LEADING_ARTICLE.sub("", text)


def string_similarity(a: str, b: str) -> float:
    """Token Jaccard for phrases; character ratio when both are one word.

    Jaccard on single words is all-or-nothing, which is exactly wrong for
    plurals and hyphenation; a character ratio catches those. Phrases get
    Jaccard so word order does not matter and one dropped word costs a bit,
    not everything.
    """
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    if len(ta) == 1 and len(tb) == 1:
        return SequenceMatcher(None, a, b).ratio()
    return len(ta & tb) / len(ta | tb)


def _verdict(verdict: str, how: str, scores: dict) -> dict:
    return {"verdict": verdict, "how": how, "scores": scores}


def grade(typed: str, reference: str, question: str, distractors: list[str],
          support: str, scorer) -> dict:
    """See the module docstring. `scorer` needs only `.rank(q, candidates, support)`."""
    t, r = normalise(typed), normalise(reference)
    if not t:
        return _verdict("wrong", "empty", {})
    if t == r:
        return _verdict("correct", "exact", {})
    similarity = string_similarity(t, r)
    if similarity >= T_STRING:
        return _verdict("correct", "string", {"similarity": similarity})
    if t in {normalise(d) for d in distractors}:
        # The distractors are the known-wrong answers for this question;
        # typing one is not ambiguous, and must not tie with itself in rule 3.
        return _verdict("wrong", "distractor", {"similarity": similarity})

    if len(r.split()) > MAX_SCORER_REFERENCE_WORDS:
        return _verdict("near", "long-reference", {"similarity": similarity})

    ranked = dict(scorer.rank(question, [typed, reference, *distractors], support))
    s_typed, s_ref = ranked[typed], ranked[reference]
    s_dmax = max((ranked[d] for d in distractors), default=0.0)
    scores = {"typed": s_typed, "reference": s_ref, "distractor_max": s_dmax,
              "similarity": similarity}
    # A scorer "correct" needs a passage to rank against. Without one its only
    # evidence is overlap with the question and length, and notebook 04 found
    # it then ranks an unrelated answer above the reference for ~12% of wrong
    # answers at any T_RATIO — so with no support the most it may say is
    # "near", which hands the case to the LLM tier or the student's override.
    # ...and a shared word with the reference: with none, the scorer has
    # nothing to anchor on ("CO2" for "carbon dioxide" is the LLM's call).
    if (support.strip() and similarity > 0
            and s_typed >= s_dmax and s_typed >= T_RATIO * s_ref):
        return _verdict("correct", "scorer", scores)
    if s_typed >= s_dmax:
        return _verdict("near", "scorer", scores)
    return _verdict("wrong", "scorer", scores)
