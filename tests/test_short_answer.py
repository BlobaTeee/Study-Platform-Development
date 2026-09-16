"""Grading a typed answer: cheap rules first, the scorer only when they can't decide."""
import importlib.util
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "ml_pipeline" / "services" / "short_answer.py")


def _load():
    spec = importlib.util.spec_from_file_location("short_answer_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sa = _load()


class StubScorer:
    """Returns the probabilities it was given, keyed by candidate text."""
    def __init__(self, probs):
        self.probs = probs
        self.calls = 0

    def rank(self, question, candidates, support):
        self.calls += 1
        return sorted(((c, self.probs[c]) for c in candidates), key=lambda t: -t[1])


class ExplodingScorer:
    def rank(self, *a, **k):
        raise AssertionError("the scorer must not be consulted for this case")


Q = "What gas do plants absorb?"
D = ["oxygen", "nitrogen", "argon"]


# ---- normalise ---------------------------------------------------------------

def test_normalise_ignores_case_punctuation_spacing_and_a_leading_article():
    assert sa.normalise("  The Carbon-Dioxide! ") == "carbon dioxide"
    assert sa.normalise("an Atom") == "atom"


def test_normalise_keeps_an_article_that_is_not_leading():
    assert sa.normalise("state of the art") == "state of the art"


# ---- rule 1: exact ------------------------------------------------------------

def test_exact_after_normalisation_is_correct_without_the_scorer():
    out = sa.grade("the carbon dioxide.", "Carbon Dioxide", Q, D, "", ExplodingScorer())
    assert (out["verdict"], out["how"]) == ("correct", "exact")


def test_an_empty_answer_is_wrong_without_the_scorer():
    out = sa.grade("   ", "carbon dioxide", Q, D, "", ExplodingScorer())
    assert (out["verdict"], out["how"]) == ("wrong", "empty")


# ---- rule 2: near-string --------------------------------------------------------

def test_a_plural_of_a_one_word_answer_is_correct_by_string():
    out = sa.grade("mitochondrias", "mitochondria", Q, D, "", ExplodingScorer())
    assert (out["verdict"], out["how"]) == ("correct", "string")


def test_a_reordered_multi_word_answer_is_correct_by_string():
    out = sa.grade("dioxide carbon", "carbon dioxide", Q, D, "", ExplodingScorer())
    assert (out["verdict"], out["how"]) == ("correct", "string")


def test_string_similarity_is_jaccard_for_phrases_and_char_ratio_for_words():
    assert sa.string_similarity("carbon dioxide gas", "carbon dioxide") == 2 / 3
    assert sa.string_similarity("cell", "cells") > 0.85
    assert sa.string_similarity("cell", "membrane") < 0.5


# ---- rule 2b: a distractor ---------------------------------------------------------

def test_a_typed_answer_that_is_a_distractor_is_wrong_without_the_scorer():
    # Distractors are the known-wrong answers; matching one is not ambiguous.
    out = sa.grade("The Oxygen", "carbon dioxide", Q, D, "", ExplodingScorer())
    assert (out["verdict"], out["how"]) == ("wrong", "distractor")


# ---- rule 3: the scorer ----------------------------------------------------------

def test_scorer_ranks_a_good_paraphrase_correct(monkeypatch):
    monkeypatch.setattr(sa, "T_RATIO", 0.8)
    scorer = StubScorer({"dioxide gas": 0.85, "carbon dioxide": 0.9,
                         "oxygen": 0.3, "nitrogen": 0.2, "argon": 0.1})
    out = sa.grade("dioxide gas", "carbon dioxide", Q, D, "support", scorer)
    assert (out["verdict"], out["how"]) == ("correct", "scorer")
    assert scorer.calls == 1


def test_scorer_puts_an_answer_above_distractors_but_below_the_bar_in_near(monkeypatch):
    monkeypatch.setattr(sa, "T_RATIO", 0.8)
    scorer = StubScorer({"gas": 0.5, "carbon dioxide": 0.9,
                         "oxygen": 0.3, "nitrogen": 0.2, "argon": 0.1})
    out = sa.grade("gas", "carbon dioxide", Q, D, "support", scorer)
    assert (out["verdict"], out["how"]) == ("near", "scorer")


def test_scorer_puts_an_answer_below_a_distractor_in_wrong(monkeypatch):
    monkeypatch.setattr(sa, "T_RATIO", 0.8)
    scorer = StubScorer({"water": 0.2, "carbon dioxide": 0.9,
                         "oxygen": 0.3, "nitrogen": 0.2, "argon": 0.1})
    out = sa.grade("water", "carbon dioxide", Q, D, "support", scorer)
    assert (out["verdict"], out["how"]) == ("wrong", "scorer")


def test_scores_are_reported_for_the_notebook_and_the_log(monkeypatch):
    monkeypatch.setattr(sa, "T_RATIO", 0.8)
    scorer = StubScorer({"gas": 0.5, "carbon dioxide": 0.9,
                         "oxygen": 0.3, "nitrogen": 0.2, "argon": 0.1})
    out = sa.grade("gas", "carbon dioxide", Q, D, "support", scorer)
    assert out["scores"] == {"typed": 0.5, "reference": 0.9, "distractor_max": 0.3,
                             "similarity": sa.string_similarity("gas", "carbon dioxide")}


# ---- the shipped thresholds are the measured ones -------------------------------

def test_thresholds_match_the_notebook_report():
    import json
    report = Path(__file__).resolve().parents[1] / "ml_pipeline" / "reports" / "short_answer_metrics.json"
    chosen = json.loads(report.read_text())["chosen"]
    assert sa.T_STRING == chosen["T_STRING"]
    assert sa.T_RATIO == chosen["T_RATIO"]
    assert chosen["precision"] >= 0.9, "the notebook's own acceptance bar"


# ---- no support: the scorer may doubt, not certify ---------------------------------

def test_without_support_the_scorer_can_only_say_near_or_wrong(monkeypatch):
    # Measured in notebook 04: with no passage the scorer ranks an unrelated
    # answer above the reference for ~12% of negatives, at any T_RATIO. So a
    # scorer "correct" needs a passage; without one the best it can do is
    # hand the case to the LLM tier / the override as `near`.
    monkeypatch.setattr(sa, "T_RATIO", 0.6)
    scorer = StubScorer({"dioxide gas": 0.95, "carbon dioxide": 0.9,
                         "oxygen": 0.3, "nitrogen": 0.2, "argon": 0.1})
    out = sa.grade("dioxide gas", "carbon dioxide", Q, D, "", scorer)
    assert (out["verdict"], out["how"]) == ("near", "scorer")
    out = sa.grade("dioxide gas", "carbon dioxide", Q, D, "Plants absorb carbon dioxide.", scorer)
    assert out["verdict"] == "correct"


# ---- the scorer only judges what it was trained on ----------------------------------

def test_a_sentence_length_reference_skips_the_scorer_and_goes_to_near(monkeypatch):
    # The scorer was trained on SciQ's 1-3 word answers. On a 14-word
    # reference it gave the reference itself 0.012 and an unrelated typed
    # answer 0.023 — "correct". Long references go to the LLM tier instead.
    monkeypatch.setattr(sa, "T_RATIO", 0.6)
    ref = "Individuals struggle with personal financial management, lacking insights into spending"
    out = sa.grade("something unrelated entirely", ref, "What is the issue?", ["a", "b"],
                   "support text", ExplodingScorer())
    assert (out["verdict"], out["how"]) == ("near", "long-reference")


def test_a_typed_answer_sharing_no_word_with_a_short_reference_cannot_be_scorer_correct(monkeypatch):
    # No shared token means the scorer has nothing to anchor on; the LLM
    # (or the override) decides — never a silent "correct".
    monkeypatch.setattr(sa, "T_RATIO", 0.6)
    scorer = StubScorer({"unrelated words": 0.95, "carbon dioxide": 0.9,
                         "oxygen": 0.3, "nitrogen": 0.2, "argon": 0.1})
    out = sa.grade("unrelated words", "carbon dioxide", Q, D, "support", scorer)
    assert (out["verdict"], out["how"]) == ("near", "scorer")
