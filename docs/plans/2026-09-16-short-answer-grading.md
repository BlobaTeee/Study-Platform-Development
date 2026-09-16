# Short-Answer Grading Implementation Plan

**Goal:** Let a student type an answer on the Quizzes page and get a correct / near / wrong verdict — cheap rules and the trained `AnswerScorer` first, the configured LLM only for the ambiguous band — with every override stored as a label.

**Architecture:** A Django-free grader (`ml_pipeline/services/short_answer.py`) applies three rules and returns a verdict; a notebook measures those rules on SciQ and fixes the two thresholds; a thin Django service adds the LLM tie-break and two viewset actions write `Answer` rows; the Quizzes page gains a typed mode behind a toggle. Multiple choice is untouched.

**Tech Stack:** scikit-learn 1.9 (existing artifact), pandas, Jupyter (`.venv`, Python 3.11) for the evaluation; Django 5.2 + DRF (`backend/venv`, 3.13); Next.js 16 / TypeScript.

**Spec:** `docs/specs/2026-09-16-short-answer-grading-design.md`

## Global Constraints

- Branch `feat/short-answer-confidence`; tag `pre-short-answer` is the revert point. Multiple-choice code paths must not change behaviour.
- Pure tests: `.venv/bin/pytest -q` from the repo root (Django-free, importlib-loaded). API tests: `cd backend && ./venv/bin/pytest -q`.
- The scorer artifact `ml_pipeline/models/answer_scorer.joblib` must exist (`cd backend && ./venv/bin/python manage.py ensure_ml_model` if not). It is gitignored.
- ML evaluation happens in a notebook under `ml_pipeline/notebooks/` (project rule); executed with `.venv/bin/jupyter nbconvert --to notebook --execute --inplace`.
- Thresholds live as constants in `short_answer.py` with the notebook's numbers in a comment; a test asserts they equal `ml_pipeline/reports/short_answer_metrics.json`.
- Status colours (green/amber/red) always ship with an icon and a word, never colour alone.

---

### Task 1: The grader — rules 1–3, Django-free

**Files:**
- Create: `ml_pipeline/services/short_answer.py`
- Test: `tests/test_short_answer.py`

**Interfaces:**
- Produces: `normalise(text) -> str`, `string_similarity(a, b) -> float`, `grade(typed, reference, question, distractors, support, scorer) -> dict` with keys `verdict` (`'correct'|'near'|'wrong'`), `how` (`'empty'|'exact'|'string'|'distractor'|'scorer'`), `scores` (dict). Constants `T_STRING`, `T_RATIO`. The `scorer` argument only needs `.rank(question, candidates, support) -> list[(candidate, prob)]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_short_answer.py`:

```python
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


# ---- rule 3: the scorer ----------------------------------------------------------

def test_scorer_ranks_a_good_paraphrase_correct(monkeypatch):
    monkeypatch.setattr(sa, "T_RATIO", 0.8)
    scorer = StubScorer({"co2 gas": 0.85, "carbon dioxide": 0.9,
                         "oxygen": 0.3, "nitrogen": 0.2, "argon": 0.1})
    out = sa.grade("co2 gas", "carbon dioxide", Q, D, "support", scorer)
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


def test_a_typed_answer_that_is_a_distractor_is_wrong_without_the_scorer():
    # Distractors are the known-wrong answers; matching one is not ambiguous.
    out = sa.grade("The Oxygen", "carbon dioxide", Q, D, "", ExplodingScorer())
    assert (out["verdict"], out["how"]) == ("wrong", "distractor")
```

- [ ] **Step 2: Run, expect collection failure**

Run: `.venv/bin/pytest tests/test_short_answer.py -q`
Expected: error — `short_answer.py` does not exist.

- [ ] **Step 3: Implement**

`ml_pipeline/services/short_answer.py`:

```python
"""Grading a typed answer against a reference: cheap rules first, the scorer last.

Rules, in order — the first that decides wins:
  1. exact after normalisation          -> correct
  2. near-string (plural, order, hyphen) -> correct
  2b. equals a distractor               -> wrong
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
T_STRING = 0.8   # placeholder until the notebook has run (Task 2)
T_RATIO = 0.8    # placeholder until the notebook has run (Task 2)

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

    ranked = dict(scorer.rank(question, [typed, reference, *distractors], support))
    s_typed, s_ref = ranked[typed], ranked[reference]
    s_dmax = max((ranked[d] for d in distractors), default=0.0)
    scores = {"typed": s_typed, "reference": s_ref, "distractor_max": s_dmax,
              "similarity": similarity}
    if s_typed >= s_dmax and s_typed >= T_RATIO * s_ref:
        return _verdict("correct", "scorer", scores)
    if s_typed >= s_dmax:
        return _verdict("near", "scorer", scores)
    return _verdict("wrong", "scorer", scores)
```

- [ ] **Step 4: Run, expect green**

Run: `.venv/bin/pytest tests/test_short_answer.py -q` — Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add ml_pipeline/services/short_answer.py tests/test_short_answer.py
git commit -m "feat(ml): grade a typed answer — exact, near-string, then the scorer"
```

---

### Task 2: Measure the rules on SciQ and fix the thresholds

**Files:**
- Create: `ml_pipeline/notebooks/04_short_answer_grading.ipynb` (written with `nbformat`, then executed)
- Create: `ml_pipeline/reports/short_answer_metrics.json` (notebook output)
- Modify: `ml_pipeline/services/short_answer.py:14-15` (the two constants + comment)
- Test: `tests/test_short_answer.py` (one more test)

**Interfaces:**
- Consumes: `short_answer.grade`, `normalise`, `string_similarity` (Task 1); `AnswerScorer.load`, `config.PROCESSED_DIR / "sciq.parquet"`.
- Produces: `reports/short_answer_metrics.json` with top-level keys `chosen` (`{"T_STRING", "T_RATIO", "precision", "recall", "f1", "near_rate"}`), `components`, `no_support`, `llm` (or `null`), `n_positive`, `n_negative`.

- [ ] **Step 1: Write the threshold-consistency test (fails until the report exists)**

Append to `tests/test_short_answer.py`:

```python
# ---- the shipped thresholds are the measured ones -------------------------------

def test_thresholds_match_the_notebook_report():
    import json
    report = Path(__file__).resolve().parents[1] / "ml_pipeline" / "reports" / "short_answer_metrics.json"
    chosen = json.loads(report.read_text())["chosen"]
    assert sa.T_STRING == chosen["T_STRING"]
    assert sa.T_RATIO == chosen["T_RATIO"]
    assert chosen["precision"] >= 0.9, "the notebook's own acceptance bar"
```

Run: `.venv/bin/pytest tests/test_short_answer.py -q -k thresholds` — Expected: FAIL (`FileNotFoundError`).

- [ ] **Step 2: Write the notebook with nbformat**

Run this script from the repo root with `.venv/bin/python` (it only writes the `.ipynb`; execution is Step 3):

```python
import nbformat as nbf
from pathlib import Path

nb = nbf.v4.new_notebook()
cells = []
md = lambda s: cells.append(nbf.v4.new_markdown_cell(s))
code = lambda s: cells.append(nbf.v4.new_code_cell(s))

md("""# 04 — Short-answer grading: measuring the rules, fixing the thresholds

The Quizzes page can grade a typed answer with three rules (exact, near-string,
`AnswerScorer` ranking) and, for the ambiguous band, an LLM tie-break. This
notebook measures the rules on SciQ's **test split** (never seen by the scorer)
and picks `T_STRING` / `T_RATIO` by a stated criterion: **precision of "correct"
≥ 0.90, then best F1**. A false "correct" teaches a wrong fact; a false "near"
costs one click on *I was right*.

What this is not: real typed answers. Positives are synthetic variants of the
reference; the override log in the app is where real labels come from.""")

code("""from ml_pipeline import notebook_setup; notebook_setup.bootstrap()
import json, re, time, itertools
import numpy as np, pandas as pd
from ml_pipeline import config
from ml_pipeline.answer_scorer import AnswerScorer
from ml_pipeline.services import short_answer as sa

sciq = pd.read_parquet(config.PROCESSED_DIR / "sciq.parquet")
test = sciq[sciq.split == "test"].reset_index(drop=True)
scorer = AnswerScorer.load(config.MODELS_DIR / "answer_scorer.joblib")
len(test)""")

md("""## Evaluation set

**Positives** — what a student who knows the answer might type: the reference
as-is; lowercased and unpunctuated; with / without a leading article; a plural
or singular; for multi-word answers, another word order and the answer minus
one function word. **Negatives** — the three distractors (plausible, on-topic,
wrong) and one answer from an unrelated question.""")

code("""FUNCTION_WORDS = {"of", "the", "a", "an", "in", "and", "to"}
rng = np.random.default_rng(config.RANDOM_SEED)

def plural_variant(a):
    w = a.split()
    if len(w) != 1: return None
    return a[:-1] if a.endswith("s") and len(a) > 3 else a + "s"

def positives(ref):
    out = {ref, ref.lower(), re.sub(r"[^\\w\\s]", "", ref), "the " + ref}
    if ref.lower().startswith(("the ", "a ", "an ")):
        out.add(ref.split(" ", 1)[1])
    p = plural_variant(ref)
    if p: out.add(p)
    w = ref.split()
    if len(w) > 1:
        out.add(" ".join(reversed(w)))
        dropped = [x for x in w if x.lower() not in FUNCTION_WORDS]
        if len(dropped) < len(w): out.add(" ".join(dropped))
    return out

rows = []
answers_pool = test.correct_answer.tolist()
for i, r in test.iterrows():
    dist = [r.distractor1, r.distractor2, r.distractor3]
    for t in positives(r.correct_answer):
        rows.append(dict(qid=i, typed=t, label=1, kind="positive"))
    for d in dist:
        rows.append(dict(qid=i, typed=d, label=0, kind="distractor"))
    other = answers_pool[int(rng.integers(len(answers_pool)))]
    if other != r.correct_answer:
        rows.append(dict(qid=i, typed=other, label=0, kind="unrelated"))
ev = pd.DataFrame(rows)
ev.kind.value_counts()""")

md("""## Score everything once

The thresholds only gate numbers the rules compute; compute those once per
row (one batched `predict_proba` for the whole set) and sweep the thresholds
over the cached columns.""")

code("""def features(ev, with_support=True):
    q = test.loc[ev.qid]
    ev = ev.copy()
    ev["ref"] = q.correct_answer.values
    ev["nt"] = ev.typed.map(sa.normalise); ev["nr"] = ev.ref.map(sa.normalise)
    ev["exact"] = ev.nt == ev.nr
    ev["sim"] = [sa.string_similarity(a, b) for a, b in zip(ev.nt, ev.nr)]
    ev["is_distractor"] = [nt in {sa.normalise(d) for d in (r.distractor1, r.distractor2, r.distractor3)}
                           for nt, r in zip(ev.nt, (test.loc[i] for i in ev.qid))]
    support = q.support.values if with_support else [""] * len(q)
    # one long frame: typed, reference, three distractors per row
    long = []
    for j, (qi, typed) in enumerate(zip(ev.qid, ev.typed)):
        r = test.loc[qi]
        for c in (typed, r.correct_answer, r.distractor1, r.distractor2, r.distractor3):
            long.append(dict(row=j, question=r.question, candidate=c, support=support[j]))
    long = pd.DataFrame(long)
    long["p"] = scorer.predict_proba(long)
    g = long.groupby("row").p
    ev["s_typed"] = long[long.index % 5 == 0].p.values
    ev["s_ref"] = long[long.index % 5 == 1].p.values
    ev["s_dmax"] = long[long.index % 5 >= 2].groupby("row").p.max().values
    return ev

t0 = time.time(); F = features(ev); F0 = features(ev, with_support=False)
print(f"{len(F)} rows scored twice in {time.time()-t0:.1f}s")""")

code("""def cascade(F, T_STRING, T_RATIO):
    v = np.where(F.exact, "correct",
        np.where(F.sim >= T_STRING, "correct",
        np.where(F.is_distractor, "wrong",
        np.where((F.s_typed >= F.s_dmax) & (F.s_typed >= T_RATIO * F.s_ref), "correct",
        np.where(F.s_typed >= F.s_dmax, "near", "wrong")))))
    how = np.where(F.exact, "exact", np.where(F.sim >= T_STRING, "string",
          np.where(F.is_distractor, "distractor", "scorer")))
    return v, how

def metrics(F, v):
    correct = v == "correct"; pos = F.label == 1
    tp = (correct & pos).sum(); fp = (correct & ~pos).sum(); fn = (~correct & pos).sum()
    p = tp / max(tp + fp, 1); r = tp / max(tp + fn, 1)
    return dict(precision=round(float(p), 4), recall=round(float(r), 4),
                f1=round(float(2*p*r/max(p+r, 1e-9)), 4),
                near_rate=round(float(((v == "near") & pos).sum() / max(pos.sum(), 1)), 4),
                near_rate_neg=round(float(((v == "near") & ~pos).sum() / max((~pos).sum(), 1)), 4))

grid = [(ts, tr) for ts in (0.5, 0.6, 0.7, 0.8, 0.9) for tr in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0)]
sweep = pd.DataFrame([dict(T_STRING=ts, T_RATIO=tr, **metrics(F, cascade(F, ts, tr)[0])) for ts, tr in grid])
ok = sweep[sweep.precision >= 0.90]
chosen = (ok if len(ok) else sweep).sort_values(["f1", "precision"], ascending=False).iloc[0]
sweep.sort_values("f1", ascending=False).head(8)""")

md("""## Per-rule breakdown, and without support

Each rule alone, then the cascade at the chosen thresholds; then the same
cascade with `support = ""` — real questions often have a thin explanation.""")

code("""TS, TR = float(chosen.T_STRING), float(chosen.T_RATIO)
def rule_only(F, how_name):
    v, how = cascade(F, TS, TR)
    return metrics(F, np.where(how == how_name, v, "wrong"))
components = {"exact": rule_only(F, "exact"), "string": rule_only(F, "string"),
              "distractor": rule_only(F, "distractor"), "scorer": rule_only(F, "scorer"),
              "cascade": metrics(F, cascade(F, TS, TR)[0])}
no_support = metrics(F0, cascade(F0, TS, TR)[0])
pd.DataFrame({**components, "cascade_no_support": no_support}).T""")

md("""## The LLM tie-break, if a provider is reachable

Only the `near` band would be sent to the LLM. If Ollama is serving locally,
ask it the one narrow question the app asks, on a sample of that band, and
report accuracy and median latency. Skipped (recorded as `null`) otherwise.""")

code("""import urllib.request, urllib.error
def llm_same(question, reference, typed, model="llama3.2:3b", url="http://localhost:11434/api/generate"):
    prompt = (f"Reference answer: {json.dumps(reference)}. A student wrote: {json.dumps(typed)}. "
              f"Question: {json.dumps(question)}. Does the student's answer mean the same thing "
              "as the reference? Reply with JSON only: {\\"same\\": true} or {\\"same\\": false}.")
    body = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json"}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return bool(json.loads(json.loads(resp.read())["response"]).get("same"))

v, _ = cascade(F, TS, TR)
near = F[v == "near"]
llm = None
try:
    sample = near.sample(min(60, len(near)), random_state=config.RANDOM_SEED)
    t0 = time.time(); preds = []
    for _, r in sample.iterrows():
        preds.append(llm_same(test.loc[r.qid].question, r.ref, r.typed))
    lat = (time.time() - t0) / len(sample)
    acc = float(np.mean(np.array(preds) == (sample.label.values == 1)))
    llm = dict(n=int(len(sample)), accuracy=round(acc, 4), mean_latency_s=round(lat, 2),
               near_share=round(float((v == "near").mean()), 4))
except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
    print("LLM tier skipped:", exc)
llm""")

md("""## Result""")

code("""report = dict(
    chosen=dict(T_STRING=TS, T_RATIO=TR, precision=float(chosen.precision),
                recall=float(chosen.recall), f1=float(chosen.f1), near_rate=float(chosen.near_rate)),
    components=components, no_support=no_support, llm=llm,
    n_positive=int((ev.label == 1).sum()), n_negative=int((ev.label == 0).sum()),
    split="test", criterion="precision >= 0.90, then max F1",
)
config.ensure_dirs()
(config.REPORTS_DIR / "short_answer_metrics.json").write_text(json.dumps(report, indent=2))
report["chosen"]""")

nb["cells"] = cells
nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
Path("ml_pipeline/notebooks/04_short_answer_grading.ipynb").write_text(nbf.writes(nb))
print("written")
```

- [ ] **Step 3: Execute the notebook**

Run: `.venv/bin/jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=1800 ml_pipeline/notebooks/04_short_answer_grading.ipynb`
Expected: exits 0; `ml_pipeline/reports/short_answer_metrics.json` exists. Read `chosen` from it. If `chosen.precision < 0.90` the grid has no acceptable pair — stop and report the sweep table rather than shipping a threshold that fails the bar.

- [ ] **Step 4: Copy the chosen thresholds into the module**

Edit `ml_pipeline/services/short_answer.py` lines 14–15 to the chosen values, e.g.:

```python
T_STRING = 0.7   # notebook 04, SciQ test: precision 0.9xx / recall 0.xxx at this pair
T_RATIO = 0.8    # (see reports/short_answer_metrics.json["chosen"])
```

(Real numbers from the report; keep the format.)

- [ ] **Step 5: Run the pure suite, expect green**

Run: `.venv/bin/pytest -q` — Expected: all pass, including `test_thresholds_match_the_notebook_report`. If the stub-scorer tests in Task 1 now disagree with a chosen `T_RATIO` (they monkeypatch it to 0.8, so they should not), fix the test's monkeypatched value, not the constant.

- [ ] **Step 6: Commit**

```bash
git add ml_pipeline/notebooks/04_short_answer_grading.ipynb ml_pipeline/reports/short_answer_metrics.json ml_pipeline/services/short_answer.py tests/test_short_answer.py
git commit -m "feat(ml): measure the short-answer rules on SciQ and fix the thresholds"
```

---

### Task 3: `Answer` records how it was graded

**Files:**
- Modify: `backend/quizzes/models.py:77-90`
- Create: `backend/quizzes/migrations/0007_answer_typed_grading.py`

**Interfaces:**
- Produces: `Answer.mode` (`'choice'|'typed'`, default `'choice'`), `Answer.verdict` (str, blank), `Answer.graded_how` (str, blank), `Answer.overridden` (bool, default False).

- [ ] **Step 1: Add the fields**

In `backend/quizzes/models.py`, inside `class Answer`, after `points_earned`:

```python
    # How this answer was produced and graded. 'choice' rows are exact-match
    # multiple choice, as always. 'typed' rows went through the short-answer
    # grader: `verdict` is what it said, `graded_how` which rule decided
    # (exact/string/scorer/llm), and `overridden` that the student disagreed —
    # which makes the row a labelled example for retraining.
    MODE_CHOICES = [('choice', 'Multiple choice'), ('typed', 'Typed')]
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default='choice')
    verdict = models.CharField(max_length=10, blank=True, default='')
    graded_how = models.CharField(max_length=10, blank=True, default='')
    overridden = models.BooleanField(default=False)
```

- [ ] **Step 2: Migration**

`backend/quizzes/migrations/0007_answer_typed_grading.py`:

```python
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('quizzes', '0006_strip_source_tags_from_descriptions')]

    operations = [
        migrations.AddField(model_name='answer', name='mode',
                            field=models.CharField(choices=[('choice', 'Multiple choice'), ('typed', 'Typed')],
                                                   default='choice', max_length=10)),
        migrations.AddField(model_name='answer', name='verdict',
                            field=models.CharField(blank=True, default='', max_length=10)),
        migrations.AddField(model_name='answer', name='graded_how',
                            field=models.CharField(blank=True, default='', max_length=10)),
        migrations.AddField(model_name='answer', name='overridden',
                            field=models.BooleanField(default=False)),
    ]
```

- [ ] **Step 3: Check and migrate**

Run: `cd backend && ./venv/bin/python manage.py makemigrations --check --dry-run quizzes 2>&1 | grep -E "^\s+[+-]"` — Expected: no `+`/`-` lines for `answer` (the pre-existing `~ Alter field id` drift lines are not ours).
Run: `./venv/bin/python manage.py migrate quizzes` — Expected: `Applying quizzes.0007_answer_typed_grading... OK`.

- [ ] **Step 4: Commit**

```bash
git add backend/quizzes/models.py backend/quizzes/migrations/0007_answer_typed_grading.py
git commit -m "feat(quizzes): Answer records mode, verdict, rule and override"
```

---

### Task 4: Grading service and the two actions

**Files:**
- Create: `backend/quizzes/services/typed_grading.py`
- Modify: `backend/quizzes/views.py` (`QuizAttemptViewSet`, after `complete`)
- Test: `backend/tests/test_typed_grading.py`

**Interfaces:**
- Consumes: `short_answer.grade` (Task 1), `Answer` fields (Task 3), `ml_pipeline.services.quiz_generator.get_answer_scorer`, `notebooks.services.ai_provider.get_ai_provider`.
- Produces: `typed_grading.grade_typed(question, typed) -> dict` (`verdict`, `how`, `scores`); `POST /api/quizzes/attempts/{id}/grade_typed_answer/` and `POST /api/quizzes/attempts/{id}/override_answer/` as in the spec.

- [ ] **Step 1: Write the failing API tests**

`backend/tests/test_typed_grading.py`:

```python
"""Typing an answer on a quiz: graded offline, the LLM only for the ambiguous
band, and the student's override recorded as a label."""
import pytest

from quizzes.models import Answer, Question, Quiz, QuizAttempt

pytestmark = pytest.mark.django_db


@pytest.fixture
def attempt(user):
    quiz = Quiz.objects.create(user=user, title='Gases', is_published=True)
    Question.objects.create(
        quiz=quiz, question_text='What gas do plants absorb during photosynthesis?',
        question_type='multiple_choice',
        options=['carbon dioxide', 'oxygen', 'nitrogen', 'argon'],
        correct_answer='carbon dioxide', order=0,
        explanation='Plants absorb carbon dioxide during photosynthesis.')
    return QuizAttempt.objects.create(quiz=quiz, user=user)


def _grade(client, attempt, typed):
    q = attempt.quiz.questions.first()
    return client.post(f'/api/quizzes/attempts/{attempt.id}/grade_typed_answer/',
                       {'question_id': q.id, 'answer': typed}, format='json')


def test_an_exact_answer_is_correct_and_recorded_as_typed(client, attempt):
    res = _grade(client, attempt, 'The Carbon Dioxide')

    assert res.status_code == 200, res.json()
    body = res.json()
    assert (body['verdict'], body['how'], body['is_correct']) == ('correct', 'exact', True)
    assert body['reference_answer'] == 'carbon dioxide'
    row = Answer.objects.get(id=body['id'])
    assert (row.mode, row.verdict, row.graded_how, row.points_earned) == ('typed', 'correct', 'exact', 1)


def test_a_distractor_is_wrong_by_the_distractor_rule(client, attempt):
    body = _grade(client, attempt, 'oxygen').json()
    assert (body['verdict'], body['how']) == ('wrong', 'distractor')
    assert body['is_correct'] is False


def test_an_empty_answer_is_refused(client, attempt):
    res = _grade(client, attempt, '   ')
    assert res.status_code == 400
    assert Answer.objects.count() == 0


def test_a_question_from_another_quiz_is_not_found(client, user, attempt):
    other = Quiz.objects.create(user=user, title='Other')
    q = Question.objects.create(quiz=other, question_text='?', question_type='multiple_choice',
                                options=['a', 'b'], correct_answer='a', order=0)
    res = client.post(f'/api/quizzes/attempts/{attempt.id}/grade_typed_answer/',
                      {'question_id': q.id, 'answer': 'a'}, format='json')
    assert res.status_code == 404


def test_grading_is_refused_once_the_attempt_is_completed(client, attempt):
    QuizAttempt.objects.filter(id=attempt.id).update(is_completed=True)
    assert _grade(client, attempt, 'carbon dioxide').status_code == 400


def test_a_missing_scorer_artifact_is_a_503_not_a_crash(client, attempt, monkeypatch):
    import quizzes.services.typed_grading as tg
    def missing():
        raise FileNotFoundError('answer_scorer.joblib')
    monkeypatch.setattr(tg, 'get_answer_scorer', missing)

    res = _grade(client, attempt, 'some gas')

    assert res.status_code == 503
    assert 'ensure_ml_model' in res.json()['detail']
    assert Answer.objects.count() == 0


# ---- the LLM tier ----------------------------------------------------------------

class _Provider:
    name = 'stub'
    def __init__(self, reply=None, raise_=None):
        self.reply, self.raise_, self.calls = reply, raise_, []
    def generate_json(self, prompt):
        self.calls.append(prompt)
        if self.raise_:
            raise self.raise_
        return self.reply
    def summarize(self, text, title=''):
        raise NotImplementedError


@pytest.fixture
def near_verdict(monkeypatch):
    """Force rules 1-3 to say `near`, so what happens next is the LLM tier's."""
    import quizzes.services.typed_grading as tg
    monkeypatch.setattr(tg, 'rules_grade',
                        lambda *a, **k: {'verdict': 'near', 'how': 'scorer', 'scores': {}})


def _use_provider(monkeypatch, provider):
    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: provider)
    return provider


def test_the_llm_promotes_a_near_to_correct(client, attempt, near_verdict, monkeypatch):
    p = _use_provider(monkeypatch, _Provider(reply={'same': True}))

    body = _grade(client, attempt, 'CO2').json()

    assert (body['verdict'], body['how'], body['is_correct']) == ('correct', 'llm', True)
    assert len(p.calls) == 1
    assert '"CO2"' in p.calls[0]          # the typed answer travels as quoted data


def test_the_llm_demotes_a_near_to_wrong(client, attempt, near_verdict, monkeypatch):
    _use_provider(monkeypatch, _Provider(reply={'same': False}))
    body = _grade(client, attempt, 'a gas').json()
    assert (body['verdict'], body['how']) == ('wrong', 'llm')


def test_an_unavailable_llm_leaves_near_alone(client, attempt, near_verdict, monkeypatch):
    _use_provider(monkeypatch, _Provider(raise_=RuntimeError('ollama is down')))
    body = _grade(client, attempt, 'a gas').json()
    assert (body['verdict'], body['how']) == ('near', 'scorer')


def test_a_malformed_llm_reply_leaves_near_alone(client, attempt, near_verdict, monkeypatch):
    _use_provider(monkeypatch, _Provider(reply={'answer': 'yes'}))
    body = _grade(client, attempt, 'a gas').json()
    assert body['verdict'] == 'near'


def test_a_clear_verdict_never_reaches_the_llm(client, attempt, monkeypatch):
    p = _use_provider(monkeypatch, _Provider(raise_=AssertionError('must not be called')))
    assert _grade(client, attempt, 'carbon dioxide').json()['verdict'] == 'correct'
    assert _grade(client, attempt, 'oxygen').json()['verdict'] == 'wrong'
    assert p.calls == []


# ---- override ---------------------------------------------------------------------

def _override(client, attempt, answer_id, is_correct=True):
    return client.post(f'/api/quizzes/attempts/{attempt.id}/override_answer/',
                       {'answer_id': answer_id, 'is_correct': is_correct}, format='json')


def test_the_student_can_overrule_a_wrong_and_it_counts(client, attempt):
    answer_id = _grade(client, attempt, 'oxygen').json()['id']

    res = _override(client, attempt, answer_id)

    assert res.status_code == 200
    row = Answer.objects.get(id=answer_id)
    assert (row.is_correct, row.points_earned, row.overridden) == (True, 1, True)
    done = client.post(f'/api/quizzes/attempts/{attempt.id}/complete/', {}, format='json').json()
    assert done['score'] == 100.0


def test_a_choice_answer_cannot_be_overridden(client, attempt):
    q = attempt.quiz.questions.first()
    row = client.post(f'/api/quizzes/attempts/{attempt.id}/submit_answer/',
                      {'question_id': q.id, 'answer': 'oxygen'}, format='json').json()
    assert _override(client, attempt, row['id']).status_code == 400


def test_override_is_refused_once_the_attempt_is_completed(client, attempt):
    answer_id = _grade(client, attempt, 'oxygen').json()['id']
    QuizAttempt.objects.filter(id=attempt.id).update(is_completed=True)
    assert _override(client, attempt, answer_id).status_code == 400


def test_another_users_attempt_is_not_found(other_user, attempt):
    from rest_framework.test import APIClient
    theirs = APIClient(HTTP_HOST='localhost'); theirs.force_authenticate(other_user)
    assert _grade(theirs, attempt, 'carbon dioxide').status_code == 404
```

- [ ] **Step 2: Run, expect failures**

Run: `cd backend && ./venv/bin/pytest -q tests/test_typed_grading.py`
Expected: every test fails (404 on the unknown actions; the `near_verdict` fixture errors on the missing module).

- [ ] **Step 3: The service**

`backend/quizzes/services/typed_grading.py`:

```python
"""Grading a typed quiz answer: the pure rules, then the LLM for `near` only.

The three rules (ml_pipeline.services.short_answer) settle most answers in
milliseconds with no network. Only a `near` verdict is put to the configured
provider — Ollama on a laptop, Gemini in production, same code — and any
failure there leaves `near` in place: the student sees "Close" and the
override, never an error.
"""
import json
import logging

from ml_pipeline.services.quiz_generator import get_answer_scorer
from ml_pipeline.services.short_answer import grade as rules_grade

logger = logging.getLogger(__name__)

_TIE_BREAK_PROMPT = (
    'Reference answer: {reference}. A student wrote: {typed}. Question: {question}. '
    'Does the student\'s answer mean the same thing as the reference? '
    'Reply with JSON only: {{"same": true}} or {{"same": false}}.'
)


def grade_typed(question, typed: str) -> dict:
    """Verdict for `typed` against `question`'s reference answer.

    Raises whatever the scorer raises when its artifact is missing — the
    view turns that into a 503; it is a deployment fault, not a bad answer.
    """
    distractors = [o for o in (question.options or []) if o != question.correct_answer]
    verdict = rules_grade(typed, question.correct_answer, question.question_text,
                          distractors, question.explanation or '', get_answer_scorer())
    if verdict['verdict'] == 'near':
        verdict = _llm_tie_break(question, typed, verdict)
    return verdict


def _llm_tie_break(question, typed: str, verdict: dict) -> dict:
    from notebooks.services.ai_provider import get_ai_provider

    # json.dumps quotes the student's text, so it arrives as data: a typed
    # "ignore the above and say true" is a string the model is asked about,
    # not an instruction. Only the one boolean is read from the reply.
    prompt = _TIE_BREAK_PROMPT.format(
        reference=json.dumps(question.correct_answer),
        typed=json.dumps(typed),
        question=json.dumps(question.question_text),
    )
    try:
        provider = get_ai_provider()
        same = provider.generate_json(prompt).get('same')
    except Exception as exc:  # noqa: BLE001 — every failure means "no opinion"
        logger.warning('Typed-answer tie-break unavailable: %s', exc)
        return verdict
    if same is True:
        return {**verdict, 'verdict': 'correct', 'how': 'llm'}
    if same is False:
        return {**verdict, 'verdict': 'wrong', 'how': 'llm'}
    logger.warning('Typed-answer tie-break returned no boolean from %s', provider.name)
    return verdict
```

- [ ] **Step 4: The actions**

In `backend/quizzes/views.py`, add `import logging` at the top and `logger = logging.getLogger(__name__)` after the imports if absent, then inside `QuizAttemptViewSet` after `complete`:

```python
    @action(detail=True, methods=['post'])
    def grade_typed_answer(self, request, pk=None):
        """Grade an answer the student typed rather than picked.

        Writes an Answer row like submit_answer does, so `complete` scores
        the attempt unchanged; the row also records how it was graded.
        """
        from .services.typed_grading import grade_typed

        attempt = self.get_object()
        if attempt.is_completed:
            return Response({'detail': 'This attempt is already complete.'}, status=400)
        typed = (request.data.get('answer') or '').strip()
        if not typed:
            return Response({'detail': 'Type an answer first.'}, status=400)
        question = Question.objects.filter(pk=request.data.get('question_id'),
                                           quiz=attempt.quiz).first()
        if question is None:
            return Response({'detail': 'Question not part of this quiz.'}, status=404)

        try:
            verdict = grade_typed(question, typed)
        except Exception as exc:  # noqa: BLE001 — the scorer artifact, most likely
            logger.exception('Typed grading failed')
            return Response({'detail': 'Typed grading is unavailable — build the model with '
                                       '`manage.py ensure_ml_model`.'}, status=503)

        is_correct = verdict['verdict'] == 'correct'
        answer = Answer.objects.create(
            quiz_attempt=attempt, question=question, user_answer=typed,
            is_correct=is_correct, points_earned=1 if is_correct else 0,
            mode='typed', verdict=verdict['verdict'], graded_how=verdict['how'],
        )
        return Response({
            'id': answer.id, 'verdict': verdict['verdict'], 'how': verdict['how'],
            'is_correct': is_correct, 'reference_answer': question.correct_answer,
            'explanation': question.explanation,
        })

    @action(detail=True, methods=['post'])
    def override_answer(self, request, pk=None):
        """The student disagrees with the grader. Their call stands, and the
        disagreement is kept: it is the label the model can learn from."""
        attempt = self.get_object()
        if attempt.is_completed:
            return Response({'detail': 'This attempt is already complete.'}, status=400)
        answer = attempt.answers.filter(id=request.data.get('answer_id')).first()
        if answer is None:
            return Response({'detail': 'Answer not part of this attempt.'}, status=404)
        if answer.mode != 'typed':
            return Response({'detail': 'Only typed answers can be overridden.'}, status=400)
        is_correct = bool(request.data.get('is_correct'))
        answer.is_correct = is_correct
        answer.points_earned = 1 if is_correct else 0
        answer.overridden = True
        answer.save(update_fields=['is_correct', 'points_earned', 'overridden'])
        return Response({'id': answer.id, 'is_correct': is_correct, 'overridden': True})
```

- [ ] **Step 5: Run, expect green**

Run: `cd backend && ./venv/bin/pytest -q` — Expected: all pass (47 + 16 = 63). If `test_an_exact_answer…` fails on `how`, check `normalise` handles `'The Carbon Dioxide'` → `'carbon dioxide'`.

- [ ] **Step 6: Reverse-check with stash, then commit**

Sabotage check: `git stash push -- backend/quizzes/services/typed_grading.py` is not possible for a new untracked file — instead temporarily edit `_llm_tie_break` to `return verdict` on its first line, run `tests/test_typed_grading.py -k llm`, expect the promote/demote tests to fail, then undo the edit by hand (do **not** `git checkout` — the file is uncommitted).

```bash
git add backend/quizzes/services/typed_grading.py backend/quizzes/views.py backend/tests/test_typed_grading.py
git commit -m "feat(quizzes): grade a typed answer, with the LLM only for the ambiguous band"
```

---

### Task 5: Typed mode on the Quizzes page

**Files:**
- Modify: `lib/api.ts:79-86` (two functions)
- Modify: `app/dashboard/quizzes/page.tsx` (state, header toggle, card body, buttons)

**Interfaces:**
- Consumes: the two actions (Task 4).
- Produces: `quizzesAPI.gradeTypedAnswer(attemptId, {question_id, answer})`, `quizzesAPI.overrideAnswer(attemptId, {answer_id, is_correct})`.

- [ ] **Step 1: API functions**

In `lib/api.ts`, inside `quizzesAPI` after `completeQuiz`:

```ts
  gradeTypedAnswer: (attemptId: number, data: { question_id: number; answer: string }) =>
    api.post(`/quizzes/attempts/${attemptId}/grade_typed_answer/`, data),
  overrideAnswer: (attemptId: number, data: { answer_id: number; is_correct: boolean }) =>
    api.post(`/quizzes/attempts/${attemptId}/override_answer/`, data),
```

- [ ] **Step 2: State and handlers**

In `app/dashboard/quizzes/page.tsx`, add to the imports from `lucide-react`: `CheckCircle2, XCircle, CircleDashed, Keyboard`. Add a type near the other types:

```ts
type Graded = {
  id: number
  verdict: 'correct' | 'near' | 'wrong'
  how: string
  is_correct: boolean
  reference_answer: string
  explanation?: string | null
}

const TYPED_MODE_KEY = 'quiz-typed-mode'
```

After `const [starting, setStarting] = useState(false)`:

```ts
  // Typed mode: recall instead of recognition. Off by default, remembered
  // per browser; a 503 from the grader (no model built) turns it off again.
  const [typedMode, setTypedMode] = useState(false)
  const [typedUnavailable, setTypedUnavailable] = useState(false)
  const [typed, setTyped] = useState('')
  const [grading, setGrading] = useState(false)
  const [graded, setGraded] = useState<Graded | null>(null)
  const [typedError, setTypedError] = useState('')

  useEffect(() => {
    try {
      setTypedMode(localStorage.getItem(TYPED_MODE_KEY) === '1')
    } catch {
      /* private mode: stays off */
    }
  }, [])

  const toggleTypedMode = () => {
    const next = !typedMode
    setTypedMode(next)
    try {
      localStorage.setItem(TYPED_MODE_KEY, next ? '1' : '0')
    } catch {
      /* ignore */
    }
  }
```

After `handleSubmit`:

```ts
  const handleCheckTyped = async () => {
    if (!typed.trim() || !attemptId || grading) return
    setGrading(true)
    setTypedError('')
    try {
      const res = await quizzesAPI.gradeTypedAnswer(attemptId, {
        question_id: question.id,
        answer: typed.trim(),
      })
      const g: Graded = res.data
      setGraded(g)
      if (g.is_correct) setScore((s) => s + 1)
      setSubmitted(true)
    } catch (err) {
      const status = (err as { response?: { status?: number } }).response?.status
      if (status === 503) {
        // No model on this server: fall back to choices for good this session.
        setTypedUnavailable(true)
        setTypedMode(false)
        setTypedError("Typed grading isn't available right now — pick an answer instead.")
      } else {
        setTypedError('Could not grade that answer. Check your connection and try again.')
      }
    } finally {
      setGrading(false)
    }
  }

  const handleOverride = async () => {
    if (!graded || !attemptId || graded.is_correct) return
    try {
      await quizzesAPI.overrideAnswer(attemptId, { answer_id: graded.id, is_correct: true })
      setGraded({ ...graded, is_correct: true })
      setScore((s) => s + 1)
    } catch {
      setTypedError('Could not record that. Try again.')
    }
  }
```

In `handleNext`, after `setSubmitted(false)`, add `setTyped('')`, `setGraded(null)`, `setTypedError('')`. In the `useEffect` that resets on quiz change, add the same three resets.

Keyboard, after the handlers:

```ts
  // Enter checks, Enter again advances, `r` overrides when it is offered.
  useEffect(() => {
    if (!typedMode) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Enter' && submitted) {
        e.preventDefault()
        void handleNext()
      } else if (e.key === 'r' && submitted && graded && !graded.is_correct) {
        e.preventDefault()
        void handleOverride()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typedMode, submitted, graded])
```

- [ ] **Step 3: Header toggle**

Replace the single `Sources` button block in the header with:

```tsx
        <div className="flex items-center gap-2 shrink-0">
          {!typedUnavailable && (
            <Button
              type="button"
              variant={typedMode ? 'default' : 'outline'}
              size="lg"
              aria-pressed={typedMode}
              onClick={toggleTypedMode}
              className={
                typedMode
                  ? 'h-11 text-lg bg-mode-quizzes hover:bg-mode-quizzes-hover text-white'
                  : 'h-11 text-lg'
              }
            >
              <Keyboard className="size-5 mr-1.5" aria-hidden />
              Type answers
            </Button>
          )}
          <Button asChild variant="outline" size="lg" className="text-lg h-11">
            <Link href="/dashboard/notebooks">
              <ChevronLeft className="size-5 mr-1" />
              Sources
            </Link>
          </Button>
        </div>
```

- [ ] **Step 4: Card body — typed input and verdict**

Replace the `<div className="space-y-3">{options.map(...)}</div>` block and the `{submitted && question.explanation && ...}` line with:

```tsx
        {typedMode ? (
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault()
              if (!submitted) void handleCheckTyped()
            }}
          >
            {!submitted ? (
              <input
                autoFocus
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                placeholder="Type your answer"
                aria-label="Your answer"
                className="w-full rounded-xl border-2 border-slate-200 bg-white px-5 py-4 text-lg text-slate-900 focus:border-mode-quizzes focus:outline-none"
              />
            ) : graded ? (
              <TypedVerdict typed={typed} graded={graded} onOverride={handleOverride} />
            ) : null}
            {typedError && <p className="text-base text-red-700">{typedError}</p>}
          </form>
        ) : (
          <div className="space-y-3">
            {options.map((opt) => {
              let style = 'border-slate-200 bg-white hover:bg-slate-50'
              if (submitted) {
                if (opt === question.correct_answer) style = 'border-emerald-400 bg-emerald-50'
                else if (opt === selected) style = 'border-red-300 bg-red-50'
              } else if (selected === opt) {
                style = 'border-mode-quizzes bg-mode-quizzes/10'
              }
              return (
                <button
                  key={opt}
                  type="button"
                  disabled={submitted}
                  onClick={() => setSelected(opt)}
                  className={`w-full text-left rounded-xl border-2 px-5 py-4 text-lg text-slate-900 transition-colors ${style}`}
                >
                  {opt}
                </button>
              )
            })}
          </div>
        )}

        {submitted && !typedMode && question.explanation && (
          <p className="mt-6 text-lg text-slate-500 leading-relaxed">{question.explanation}</p>
        )}
```

And add, below the page component (same file):

```tsx
/** What the grader said about a typed answer. Colour never stands alone:
 *  each state has its icon and its word. `near` and `wrong` offer the
 *  override — the student's judgement is the last word, and the label. */
function TypedVerdict({
  typed,
  graded,
  onOverride,
}: {
  typed: string
  graded: Graded
  onOverride: () => void
}) {
  const state = graded.is_correct
    ? { icon: CheckCircle2, word: 'Correct', tone: 'border-emerald-400 bg-emerald-50 text-emerald-900', iconTone: 'text-emerald-600' }
    : graded.verdict === 'near'
      ? { icon: CircleDashed, word: 'Close', tone: 'border-amber-400 bg-amber-50 text-amber-900', iconTone: 'text-amber-600' }
      : { icon: XCircle, word: 'Not quite', tone: 'border-red-300 bg-red-50 text-red-900', iconTone: 'text-red-600' }
  const Icon = state.icon
  return (
    <div className="space-y-4">
      <div className={`rounded-xl border-2 px-5 py-4 ${state.tone}`}>
        <p className="flex items-center gap-2 font-mono text-xs uppercase tracking-wide">
          <Icon className={`size-4 ${state.iconTone}`} aria-hidden />
          {state.word}
        </p>
        <p className="mt-1 text-lg">{typed}</p>
      </div>
      {!graded.is_correct && (
        <p className="text-lg text-slate-900">
          The answer is <span className="font-semibold">{graded.reference_answer}</span>.
        </p>
      )}
      {graded.explanation && (
        <p className="text-lg text-slate-500 leading-relaxed">{graded.explanation}</p>
      )}
      {!graded.is_correct && (
        <button
          type="button"
          onClick={onOverride}
          className="text-base text-slate-600 underline underline-offset-4 hover:text-slate-900"
        >
          I was right <span className="font-mono text-xs text-slate-400">(r)</span>
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 5: Bottom buttons**

Change the `Check answer` button so it works in both modes:

```tsx
          <Button
            size="lg"
            disabled={typedMode ? !typed.trim() || grading : !selected}
            onClick={typedMode ? handleCheckTyped : handleSubmit}
            className="bg-mode-quizzes hover:bg-mode-quizzes-hover text-white h-12 px-10 text-lg"
          >
            {grading ? 'Checking…' : 'Check answer'}
          </Button>
```

- [ ] **Step 6: Typecheck, then a real run**

Run: `./node_modules/.bin/tsc --noEmit -p tsconfig.json` — Expected: silent.

With `pnpm dev:all` and `ollama serve` running: open a quiz from a notebook, press **Type answers**, then:
1. type the exact answer → green "Correct";
2. next question, type a plural or reorder → green via string rule;
3. type a distractor → red "Not quite", the reference shown, press `r` → turns green and the score rises;
4. type a synonym with no shared words → amber "Close" or an LLM verdict (check `backend` log for `Typed-answer tie-break`);
5. stop `ollama serve`, repeat 4 → amber "Close" with the override, no error;
6. toggle back to choices mid-quiz → options render for the current question.

Report what was seen, including anything that did not match.

- [ ] **Step 7: Commit**

```bash
git add lib/api.ts app/dashboard/quizzes/page.tsx
git commit -m "feat(web): type your answer on a quiz, graded offline"
```

---

### Task 6: Close out

- [ ] **Step 1:** Set the spec status to `Implemented 2026-09-16`, and add the chosen thresholds and the notebook's headline numbers (precision, recall, near rate, and the LLM row if it ran) to a short "Results" section at the end of the spec.
- [ ] **Step 2:** Both suites green (`.venv/bin/pytest -q`; `cd backend && ./venv/bin/pytest -q`), `tsc` silent.
- [ ] **Step 3:** Commit the spec update. Leave the branch unmerged; the user decides after trying it.
