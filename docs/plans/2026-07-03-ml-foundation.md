# ML Foundation Implementation Plan

**Goal:** Build the `ml_pipeline` package: process SciQ + AI Flashcards to parquet, build a topic hierarchy, and train/evaluate a classical "answer scorer" (correct-answer vs. distractor) with engineered features — the StudyFlow ML foundation.

**Architecture:** Pure, testable Python modules hold all data-cleaning, feature, and training logic; three thin Jupyter notebooks call them for EDA/preprocess/train. The trained model is an `AnswerScorer` bundling a fitted TF-IDF vectorizer + `StandardScaler` + a scikit-learn classifier chosen via a bake-off, persisted with joblib. No Django wiring in this plan.

**Tech Stack:** Python 3.11, pandas, scikit-learn, pyarrow (parquet), spaCy + textstat (EDA features), joblib, pytest, Jupyter.

## Global Constraints

- Package lives at repo root as `ml_pipeline/` and must be importable (the Django adapter inserts repo root into `sys.path`). Verbatim from spec §3.
- `ml_pipeline.config.PROCESSED_DIR` resolves to `<repo>/datasets/processed/`. Processed filenames exactly: `sciq.parquet`, `flashcards.parquet`, `topic_hierarchy.parquet`. Verbatim from spec §3/§4.
- `retrain_from_platform.retrain_all(platform_cards, sciq_df, hierarchy_df, flashcards_df)` must exist and return a `{name: info}` dict. Verbatim from spec §3.
- Classical scikit-learn only — no deep learning/embeddings. Spec §2.
- `RANDOM_SEED = 42` everywhere; fit vectorizer/scaler on **train only**; touch test split once. Spec §6.
- Respect SciQ official splits (disjoint by question); drop empty-support rows. Spec §5.1.
- All commands run with the repo `.venv`: `.venv/bin/python` / `.venv/bin/pytest`. `pytest` must be installed (Task 1).
- Use the repo `.venv` interpreter; do not create a new environment.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `ml_pipeline/__init__.py` | Package marker |
| `ml_pipeline/config.py` | Paths, seeds, dataset locations, TF-IDF constants, `ensure_dirs()` |
| `ml_pipeline/dataset_loader.py` | Load raw CSVs; `clean_sciq`, `clean_ai_flashcards`, `build_topic_hierarchy`, `build_processed_datasets`, parquet loaders |
| `ml_pipeline/eda/text_features.py` | Readability/length/token features for EDA |
| `ml_pipeline/features/answer_features.py` | `expand_candidates`, `FeatureBuilder` (engineered feature matrix) |
| `ml_pipeline/answer_scorer.py` | `AnswerScorer` — fit/score/rank/save/load |
| `ml_pipeline/train_models.py` | `train_all()` bake-off + evaluation + artifact saving; CLI entry |
| `ml_pipeline/retrain_from_platform.py` | `retrain_all()` — base retrain wrapper |
| `ml_pipeline/notebook_setup.py` | sys.path + seed bootstrap for notebooks |
| `ml_pipeline/services/__init__.py` | Empty package (later specs) |
| `ml_pipeline/README.md` | How to run end-to-end |
| `ml_pipeline/notebooks/0{1,2,3}_*.ipynb` | EDA / preprocess / train-eval |
| `tests/conftest.py` | Shared fixtures (tiny SciQ/AIF DataFrames) |
| `tests/test_*.py` | Unit tests per module |
| `pyproject.toml` | Add pytest dev dep + pytest config |
| `.gitignore` | Ignore model binaries + processed parquet |

---

## Task 1: Package scaffold, config, dev tooling

**Files:**
- Create: `ml_pipeline/__init__.py`, `ml_pipeline/config.py`, `ml_pipeline/services/__init__.py`, `ml_pipeline/eda/__init__.py`, `ml_pipeline/features/__init__.py`
- Create: `tests/conftest.py`, `tests/test_config.py`
- Modify: `pyproject.toml` (add pytest dep + config), `.gitignore`

**Interfaces:**
- Produces: `ml_pipeline.config` with `REPO_ROOT, RAW_DIR, PROCESSED_DIR, MODELS_DIR, REPORTS_DIR, RANDOM_SEED` (Path/int), `SCIQ_FILES: dict[str, Path]`, `AIF_DIR: Path`, `AIF_GLOB: str`, `TFIDF_MAX_FEATURES: int`, `TFIDF_NGRAM: tuple`, and `ensure_dirs() -> None`.

- [ ] **Step 1: Add pytest and pytest config to `pyproject.toml`**

Add an optional dev dependency group and pytest config (append to the existing file):

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

Install it:

```bash
.venv/bin/python -m pip install -e ".[dev]"
```

Expected: installs pytest into `.venv`.

- [ ] **Step 2: Add `.gitignore` rules for regenerable binaries**

Append to `.gitignore`:

```gitignore
# ML pipeline regenerable artifacts
ml_pipeline/models/*.joblib
datasets/processed/*.parquet
```

- [ ] **Step 3: Write the failing test** `tests/test_config.py`

```python
from pathlib import Path
from ml_pipeline import config


def test_processed_dir_points_at_datasets_processed():
    assert config.PROCESSED_DIR == config.REPO_ROOT / "datasets" / "processed"
    assert config.PROCESSED_DIR.name == "processed"


def test_sciq_files_are_named_correctly():
    assert set(config.SCIQ_FILES) == {"train", "val", "test"}
    for p in config.SCIQ_FILES.values():
        assert isinstance(p, Path)


def test_ensure_dirs_creates_output_dirs(tmp_path, monkeypatch):
    for name in ("PROCESSED_DIR", "MODELS_DIR", "REPORTS_DIR"):
        monkeypatch.setattr(config, name, tmp_path / name.lower())
    config.ensure_dirs()
    for name in ("PROCESSED_DIR", "MODELS_DIR", "REPORTS_DIR"):
        assert getattr(config, name).is_dir()
```

- [ ] **Step 4: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: ml_pipeline` (package not created yet).

- [ ] **Step 5: Create the package files**

`ml_pipeline/__init__.py`:

```python
"""StudyFlow ML pipeline package."""
```

`ml_pipeline/services/__init__.py`, `ml_pipeline/eda/__init__.py`, `ml_pipeline/features/__init__.py`: each a one-line docstring:

```python
"""Subpackage placeholder."""
```

`ml_pipeline/config.py`:

```python
"""Central paths, seeds, and constants for the ML pipeline."""
from __future__ import annotations

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent

RAW_DIR = REPO_ROOT / "datasets" / "raw"
PROCESSED_DIR = REPO_ROOT / "datasets" / "processed"
MODELS_DIR = PACKAGE_DIR / "models"
REPORTS_DIR = PACKAGE_DIR / "reports"

RANDOM_SEED = 42

SCIQ_DIR = RAW_DIR / "SciQ"
SCIQ_FILES = {
    "train": SCIQ_DIR / "SciQ Train Data.csv",
    "val": SCIQ_DIR / "SciQ Validation.csv",
    "test": SCIQ_DIR / "SciQ Test Data.csv",
}

AIF_DIR = RAW_DIR / "AI Flashcards"
AIF_GLOB = "*Part*.csv"

TFIDF_MAX_FEATURES = 20000
TFIDF_NGRAM = (1, 2)

PROCESSED_FILES = {
    "sciq": PROCESSED_DIR / "sciq.parquet",
    "flashcards": PROCESSED_DIR / "flashcards.parquet",
    "topic_hierarchy": PROCESSED_DIR / "topic_hierarchy.parquet",
}


def ensure_dirs() -> None:
    """Create output directories if missing."""
    for d in (PROCESSED_DIR, MODELS_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
```

`tests/conftest.py` (start it now; extended in later tasks):

```python
import pandas as pd
import pytest


@pytest.fixture
def sciq_raw_df():
    """Tiny SciQ-shaped frame: 3 questions, one with empty support."""
    return pd.DataFrame(
        {
            "question": ["What gas do plants absorb?", "What is water made of?", "Speed unit?"],
            "correct_answer": ["carbon dioxide", "hydrogen and oxygen", "meters per second"],
            "distractor1": ["oxygen", "helium", "kilograms"],
            "distractor2": ["nitrogen", "carbon", "seconds"],
            "distractor3": ["argon", "iron", "newtons"],
            "support": [
                "Plants absorb carbon dioxide from the air during photosynthesis.",
                "Water is made of hydrogen and oxygen atoms.",
                "   ",  # empty/whitespace support -> dropped
            ],
        }
    )


@pytest.fixture
def aif_raw_df():
    """Tiny AI-Flashcards-shaped frame with en/ur rows and a duplicate."""
    base = {
        "subject": "Mathematics",
        "topic": "Calculus",
        "subtopic": "Continuity",
        "difficulty": "hard",
        "bloom_level": "Understand",
        "cognitive_skill": "Comprehension",
        "source_type": "lecture_note",
        "source_text": "Continuity is a key concept in Calculus.",
        "summary": "Summary of continuity.",
        "question": "What is Continuity?",
        "answer": "A core concept.",
        "token_estimate": 40,
    }
    rows = [
        {**base, "language": "en"},
        {**base, "language": "en"},  # exact duplicate -> deduped
        {**base, "language": "ur", "source_text": "Continuity [ur]"},
        {**base, "subtopic": "Limits", "language": "en", "source_text": "Limits in Calculus."},
    ]
    return pd.DataFrame([{"id": i, **r} for i, r in enumerate(rows)])
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_config.py -q`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add ml_pipeline/__init__.py ml_pipeline/config.py ml_pipeline/services/__init__.py ml_pipeline/eda/__init__.py ml_pipeline/features/__init__.py tests/conftest.py tests/test_config.py pyproject.toml .gitignore
git commit -m "feat(ml): scaffold ml_pipeline package + config + pytest"
```

---

## Task 2: SciQ cleaning

**Files:**
- Modify: `ml_pipeline/dataset_loader.py` (create)
- Test: `tests/test_dataset_loader_sciq.py`

**Interfaces:**
- Consumes: `ml_pipeline.config`
- Produces:
  - `clean_sciq(df: pd.DataFrame, split: str) -> pd.DataFrame` — returns columns `["question","correct_answer","distractor1","distractor2","distractor3","support","split"]`, whitespace-only/NaN `support` rows dropped, `split` set to the given value, index reset.
  - `load_raw_sciq() -> pd.DataFrame` — reads `config.SCIQ_FILES`, applies `clean_sciq` per split, concatenates.

- [ ] **Step 1: Write the failing test** `tests/test_dataset_loader_sciq.py`

```python
from ml_pipeline.dataset_loader import clean_sciq


def test_clean_sciq_drops_empty_support_and_tags_split(sciq_raw_df):
    out = clean_sciq(sciq_raw_df, split="train")
    assert len(out) == 2  # the whitespace-support row is dropped
    assert set(out.columns) == {
        "question", "correct_answer", "distractor1", "distractor2",
        "distractor3", "support", "split",
    }
    assert (out["split"] == "train").all()
    assert out["support"].str.strip().astype(bool).all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_dataset_loader_sciq.py -q`
Expected: FAIL — `ModuleNotFoundError`/`ImportError: cannot import name 'clean_sciq'`.

- [ ] **Step 3: Write minimal implementation** — create `ml_pipeline/dataset_loader.py`

```python
"""Load and clean the raw datasets into tidy frames and parquet files."""
from __future__ import annotations

import glob

import pandas as pd

from . import config

SCIQ_COLUMNS = [
    "question", "correct_answer", "distractor1", "distractor2",
    "distractor3", "support",
]


def clean_sciq(df: pd.DataFrame, split: str) -> pd.DataFrame:
    """Normalize SciQ columns, drop empty-support rows, tag the split."""
    out = df.copy()
    out = out[SCIQ_COLUMNS]
    support = out["support"].fillna("").astype(str).str.strip()
    out = out[support != ""].copy()
    out["support"] = out["support"].astype(str).str.strip()
    out["split"] = split
    return out.reset_index(drop=True)


def load_raw_sciq() -> pd.DataFrame:
    """Read the three official SciQ CSVs and return one cleaned frame."""
    frames = [clean_sciq(pd.read_csv(path), split=split)
              for split, path in config.SCIQ_FILES.items()]
    return pd.concat(frames, ignore_index=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_dataset_loader_sciq.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ml_pipeline/dataset_loader.py tests/test_dataset_loader_sciq.py
git commit -m "feat(ml): SciQ cleaning loader"
```

---

## Task 3: AI Flashcards cleaning + topic hierarchy

**Files:**
- Modify: `ml_pipeline/dataset_loader.py`
- Test: `tests/test_dataset_loader_aif.py`

**Interfaces:**
- Consumes: `ml_pipeline.config`
- Produces:
  - `clean_ai_flashcards(df: pd.DataFrame) -> pd.DataFrame` — English-only, full-row dedup, columns `["subject","topic","subtopic","difficulty","source_text","summary","question","answer"]`, index reset.
  - `build_topic_hierarchy(df: pd.DataFrame) -> pd.DataFrame` — unique `subject/topic/subtopic` triples with a `count` column, sorted.
  - `load_raw_ai_flashcards() -> pd.DataFrame` — read+concat `config.AIF_DIR` parts (raw, unfiltered).

- [ ] **Step 1: Write the failing test** `tests/test_dataset_loader_aif.py`

```python
from ml_pipeline.dataset_loader import build_topic_hierarchy, clean_ai_flashcards


def test_clean_aif_english_only_and_dedup(aif_raw_df):
    out = clean_ai_flashcards(aif_raw_df)
    # 4 raw rows: 2 identical en (->1), 1 ur (dropped), 1 distinct en -> total 2
    assert len(out) == 2
    assert set(out.columns) == {
        "subject", "topic", "subtopic", "difficulty",
        "source_text", "summary", "question", "answer",
    }
    assert "language" not in out.columns


def test_build_topic_hierarchy_counts_triples(aif_raw_df):
    cleaned = clean_ai_flashcards(aif_raw_df)
    hier = build_topic_hierarchy(cleaned)
    assert set(hier.columns) == {"subject", "topic", "subtopic", "count"}
    assert len(hier) == 2  # Continuity + Limits
    assert hier["count"].sum() == len(cleaned)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_dataset_loader_aif.py -q`
Expected: FAIL — `ImportError: cannot import name 'clean_ai_flashcards'`.

- [ ] **Step 3: Write minimal implementation** — append to `ml_pipeline/dataset_loader.py`

```python
AIF_KEEP_COLUMNS = [
    "subject", "topic", "subtopic", "difficulty",
    "source_text", "summary", "question", "answer",
]


def load_raw_ai_flashcards() -> pd.DataFrame:
    """Read and concatenate the AI Flashcards CSV parts (raw)."""
    paths = sorted(glob.glob(str(config.AIF_DIR / config.AIF_GLOB)))
    if not paths:
        raise FileNotFoundError(f"No AI Flashcards parts under {config.AIF_DIR}")
    return pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)


def clean_ai_flashcards(df: pd.DataFrame) -> pd.DataFrame:
    """English-only content rows, de-duplicated, content columns only."""
    out = df[df["language"] == "en"].copy()
    out = out[AIF_KEEP_COLUMNS].drop_duplicates().reset_index(drop=True)
    return out


def build_topic_hierarchy(df: pd.DataFrame) -> pd.DataFrame:
    """Unique subject/topic/subtopic triples with occurrence counts."""
    hier = (
        df.groupby(["subject", "topic", "subtopic"])
        .size()
        .reset_index(name="count")
        .sort_values(["subject", "topic", "subtopic"])
        .reset_index(drop=True)
    )
    return hier
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_dataset_loader_aif.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ml_pipeline/dataset_loader.py tests/test_dataset_loader_aif.py
git commit -m "feat(ml): AI Flashcards cleaning + topic hierarchy"
```

---

## Task 4: Write processed parquet datasets

**Files:**
- Modify: `ml_pipeline/dataset_loader.py`
- Test: `tests/test_build_processed.py`

**Interfaces:**
- Consumes: `load_raw_sciq`, `clean_ai_flashcards`, `load_raw_ai_flashcards`, `build_topic_hierarchy`, `config`
- Produces:
  - `write_processed(sciq_df, flashcards_df, hierarchy_df) -> dict[str, Path]` — writes the three parquet files to `config.PROCESSED_FILES`, returns the path map.
  - `build_processed_datasets() -> dict[str, Path]` — full raw→parquet pipeline (used by the preprocess notebook and headless).
  - `load_processed(name: str) -> pd.DataFrame` — read one of `sciq`/`flashcards`/`topic_hierarchy`.

- [ ] **Step 1: Write the failing test** `tests/test_build_processed.py`

```python
import pandas as pd

from ml_pipeline import config, dataset_loader


def test_write_and_load_processed(tmp_path, monkeypatch, sciq_raw_df, aif_raw_df):
    files = {
        "sciq": tmp_path / "sciq.parquet",
        "flashcards": tmp_path / "flashcards.parquet",
        "topic_hierarchy": tmp_path / "topic_hierarchy.parquet",
    }
    monkeypatch.setattr(config, "PROCESSED_FILES", files)
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)

    sciq = dataset_loader.clean_sciq(sciq_raw_df, split="train")
    flash = dataset_loader.clean_ai_flashcards(aif_raw_df)
    hier = dataset_loader.build_topic_hierarchy(flash)

    paths = dataset_loader.write_processed(sciq, flash, hier)
    assert all(p.exists() for p in paths.values())

    reloaded = dataset_loader.load_processed("sciq")
    assert list(reloaded.columns) == list(sciq.columns)
    assert len(reloaded) == len(sciq)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_build_processed.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'write_processed'`.

- [ ] **Step 3: Write minimal implementation** — append to `ml_pipeline/dataset_loader.py`

```python
def write_processed(sciq_df, flashcards_df, hierarchy_df) -> dict:
    """Persist the three processed frames as parquet."""
    config.ensure_dirs()
    sciq_df.to_parquet(config.PROCESSED_FILES["sciq"], index=False)
    flashcards_df.to_parquet(config.PROCESSED_FILES["flashcards"], index=False)
    hierarchy_df.to_parquet(config.PROCESSED_FILES["topic_hierarchy"], index=False)
    return dict(config.PROCESSED_FILES)


def build_processed_datasets() -> dict:
    """Full raw -> cleaned -> parquet pipeline."""
    sciq_df = load_raw_sciq()
    flashcards_df = clean_ai_flashcards(load_raw_ai_flashcards())
    hierarchy_df = build_topic_hierarchy(flashcards_df)
    return write_processed(sciq_df, flashcards_df, hierarchy_df)


def load_processed(name: str) -> pd.DataFrame:
    """Load a processed parquet by logical name."""
    return pd.read_parquet(config.PROCESSED_FILES[name])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_build_processed.py -q`
Expected: PASS.

- [ ] **Step 5: Build the real processed datasets (verification, one-off)**

Run: `.venv/bin/python -c "from ml_pipeline.dataset_loader import build_processed_datasets as b; print({k: str(v) for k,v in b().items()})"`
Expected: prints the three parquet paths; files exist under `datasets/processed/`.

Sanity-check row counts:

Run: `.venv/bin/python -c "from ml_pipeline.dataset_loader import load_processed as L; print('sciq', len(L('sciq'))); print('flash', len(L('flashcards'))); print('hier', len(L('topic_hierarchy')))"`
Expected: `sciq` ≈ 12,352 (13,679 minus ~1,327 empty-support), `flash` ≈ 2,500–100,119, `hier` = 157.

- [ ] **Step 6: Commit**

```bash
git add ml_pipeline/dataset_loader.py tests/test_build_processed.py
git commit -m "feat(ml): build processed parquet datasets"
```

---

## Task 5: EDA text features

**Files:**
- Create: `ml_pipeline/eda/text_features.py`
- Test: `tests/test_text_features.py`

**Interfaces:**
- Produces: `text_stats(text: str) -> dict` with keys `n_chars, n_tokens, n_sentences, flesch_reading_ease`. Uses `textstat`; splits tokens on whitespace.

- [ ] **Step 1: Write the failing test** `tests/test_text_features.py`

```python
from ml_pipeline.eda.text_features import text_stats


def test_text_stats_basic():
    s = text_stats("Cells divide. DNA replicates during mitosis.")
    assert s["n_chars"] > 0
    assert s["n_tokens"] == 6
    assert s["n_sentences"] >= 2
    assert isinstance(s["flesch_reading_ease"], float)


def test_text_stats_empty_is_safe():
    s = text_stats("")
    assert s["n_tokens"] == 0
    assert s["n_chars"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_text_features.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation** — `ml_pipeline/eda/text_features.py`

```python
"""Lightweight text descriptors for exploratory data analysis."""
from __future__ import annotations

import textstat


def text_stats(text: str) -> dict:
    """Return basic length/readability stats for a piece of text."""
    text = text or ""
    tokens = text.split()
    if not tokens:
        return {"n_chars": 0, "n_tokens": 0, "n_sentences": 0,
                "flesch_reading_ease": 0.0}
    return {
        "n_chars": len(text),
        "n_tokens": len(tokens),
        "n_sentences": max(1, textstat.sentence_count(text)),
        "flesch_reading_ease": float(textstat.flesch_reading_ease(text)),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_text_features.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ml_pipeline/eda/text_features.py tests/test_text_features.py
git commit -m "feat(ml): EDA text feature helpers"
```

---

## Task 6: Candidate expansion

**Files:**
- Create: `ml_pipeline/features/answer_features.py`
- Test: `tests/test_candidate_expansion.py`

**Interfaces:**
- Produces: `expand_candidates(sciq_df: pd.DataFrame) -> pd.DataFrame` — one row per (question, candidate). Columns: `question_id, question, candidate, support, split, is_correct`. Each source row yields 4 rows (1 correct + 3 distractors); `question_id` is the source row's positional index.

- [ ] **Step 1: Write the failing test** `tests/test_candidate_expansion.py`

```python
from ml_pipeline.dataset_loader import clean_sciq
from ml_pipeline.features.answer_features import expand_candidates


def test_expand_candidates_shape_and_labels(sciq_raw_df):
    sciq = clean_sciq(sciq_raw_df, split="train")  # 2 questions survive
    long = expand_candidates(sciq)
    assert len(long) == len(sciq) * 4
    assert set(long.columns) == {
        "question_id", "question", "candidate", "support", "split", "is_correct",
    }
    # exactly one correct per question
    per_q = long.groupby("question_id")["is_correct"].sum()
    assert (per_q == 1).all()
    # correct candidate matches the source correct_answer
    first = long[long["question_id"] == long["question_id"].iloc[0]]
    correct = first[first["is_correct"] == 1]["candidate"].iloc[0]
    assert correct == sciq["correct_answer"].iloc[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_candidate_expansion.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation** — `ml_pipeline/features/answer_features.py`

```python
"""Expand SciQ rows into (question, candidate) examples and build features."""
from __future__ import annotations

import numpy as np
import pandas as pd

_DISTRACTORS = ["distractor1", "distractor2", "distractor3"]


def expand_candidates(sciq_df: pd.DataFrame) -> pd.DataFrame:
    """One row per candidate answer; is_correct=1 for the correct answer."""
    records = []
    for qid, row in enumerate(sciq_df.itertuples(index=False)):
        base = {"question_id": qid, "question": row.question,
                "support": row.support, "split": row.split}
        records.append({**base, "candidate": row.correct_answer, "is_correct": 1})
        for col in _DISTRACTORS:
            records.append({**base, "candidate": getattr(row, col), "is_correct": 0})
    return pd.DataFrame.from_records(records)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_candidate_expansion.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ml_pipeline/features/answer_features.py tests/test_candidate_expansion.py
git commit -m "feat(ml): SciQ candidate expansion"
```

---

## Task 7: Engineered feature builder

**Files:**
- Modify: `ml_pipeline/features/answer_features.py`
- Test: `tests/test_feature_builder.py`

**Interfaces:**
- Consumes: `expand_candidates`, `config`
- Produces: `class FeatureBuilder`:
  - `FEATURE_NAMES: list[str]` = `["cand_support_cos","cand_question_cos","cand_support_overlap","cand_question_overlap","cand_len_tokens","cand_len_chars","cand_is_numeric","support_len_tokens"]`
  - `.fit(long_df) -> FeatureBuilder` (fits TF-IDF on train `support`+`question` corpus)
  - `.transform(long_df) -> np.ndarray` shape `(n, 8)`

- [ ] **Step 1: Write the failing test** `tests/test_feature_builder.py`

```python
import numpy as np

from ml_pipeline.dataset_loader import clean_sciq
from ml_pipeline.features.answer_features import FeatureBuilder, expand_candidates


def test_feature_builder_correct_beats_distractor_on_support_overlap(sciq_raw_df):
    sciq = clean_sciq(sciq_raw_df, split="train")
    long = expand_candidates(sciq)
    fb = FeatureBuilder().fit(long)
    X = fb.transform(long)
    assert X.shape == (len(long), len(FeatureBuilder.FEATURE_NAMES))
    assert not np.isnan(X).any()

    overlap = X[:, FeatureBuilder.FEATURE_NAMES.index("cand_support_overlap")]
    q0 = long["question_id"] == 0
    correct_overlap = overlap[q0.values & (long["is_correct"] == 1).values]
    distractor_overlap = overlap[q0.values & (long["is_correct"] == 0).values]
    # "carbon dioxide" is in the support; distractors are not
    assert correct_overlap.max() > distractor_overlap.max()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_feature_builder.py -q`
Expected: FAIL — `ImportError: cannot import name 'FeatureBuilder'`.

- [ ] **Step 3: Write minimal implementation** — append to `ml_pipeline/features/answer_features.py`

```python
from sklearn.feature_extraction.text import TfidfVectorizer

from .. import config


def _tokens(text: str) -> set:
    return set(str(text).lower().split())


def _overlap(candidate: str, context: str) -> float:
    cand = _tokens(candidate)
    if not cand:
        return 0.0
    return len(cand & _tokens(context)) / len(cand)


def _row_cosine(a_vecs, b_vecs) -> np.ndarray:
    """Row-wise cosine similarity between two aligned sparse TF-IDF matrices."""
    num = np.asarray(a_vecs.multiply(b_vecs).sum(axis=1)).ravel()
    na = np.sqrt(np.asarray(a_vecs.multiply(a_vecs).sum(axis=1)).ravel())
    nb = np.sqrt(np.asarray(b_vecs.multiply(b_vecs).sum(axis=1)).ravel())
    denom = na * nb
    return np.divide(num, denom, out=np.zeros_like(num), where=denom > 0)


class FeatureBuilder:
    """Builds an engineered dense feature matrix for candidate answers."""

    FEATURE_NAMES = [
        "cand_support_cos", "cand_question_cos",
        "cand_support_overlap", "cand_question_overlap",
        "cand_len_tokens", "cand_len_chars",
        "cand_is_numeric", "support_len_tokens",
    ]

    def __init__(self):
        self.vectorizer: TfidfVectorizer | None = None

    def fit(self, long_df: pd.DataFrame) -> "FeatureBuilder":
        corpus = pd.concat([long_df["support"], long_df["question"]]).astype(str)
        self.vectorizer = TfidfVectorizer(
            max_features=config.TFIDF_MAX_FEATURES,
            ngram_range=config.TFIDF_NGRAM,
            stop_words="english",
        ).fit(corpus)
        return self

    def transform(self, long_df: pd.DataFrame) -> np.ndarray:
        if self.vectorizer is None:
            raise RuntimeError("FeatureBuilder.transform called before fit")
        cand = long_df["candidate"].astype(str)
        support = long_df["support"].astype(str)
        question = long_df["question"].astype(str)

        cv, sv, qv = (self.vectorizer.transform(x) for x in (cand, support, question))
        cand_support_cos = _row_cosine(cv, sv)
        cand_question_cos = _row_cosine(cv, qv)

        cand_support_overlap = np.array(
            [_overlap(c, s) for c, s in zip(cand, support)])
        cand_question_overlap = np.array(
            [_overlap(c, q) for c, q in zip(cand, question)])
        cand_len_tokens = cand.str.split().str.len().to_numpy(dtype=float)
        cand_len_chars = cand.str.len().to_numpy(dtype=float)
        cand_is_numeric = cand.str.replace(".", "", regex=False).str.strip().str.isdigit().to_numpy(dtype=float)
        support_len_tokens = support.str.split().str.len().to_numpy(dtype=float)

        return np.column_stack([
            cand_support_cos, cand_question_cos,
            cand_support_overlap, cand_question_overlap,
            cand_len_tokens, cand_len_chars,
            cand_is_numeric, support_len_tokens,
        ])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_feature_builder.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ml_pipeline/features/answer_features.py tests/test_feature_builder.py
git commit -m "feat(ml): engineered answer feature builder"
```

---

## Task 8: AnswerScorer (fit/score/rank/save/load)

**Files:**
- Create: `ml_pipeline/answer_scorer.py`
- Test: `tests/test_answer_scorer.py`

**Interfaces:**
- Consumes: `FeatureBuilder`, `expand_candidates`, `config`
- Produces: `class AnswerScorer`:
  - `AnswerScorer(classifier=None)` — defaults to `LogisticRegression(class_weight="balanced", max_iter=1000, random_state=config.RANDOM_SEED)`
  - `.fit(train_long_df) -> AnswerScorer`
  - `.predict_proba(long_df) -> np.ndarray` (P(correct) per row)
  - `.score(question, candidate, support) -> float`
  - `.rank(question, candidates, support) -> list[tuple[str, float]]` (desc)
  - `.save(path)` / `AnswerScorer.load(path) -> AnswerScorer`

- [ ] **Step 1: Write the failing test** `tests/test_answer_scorer.py`

```python
from ml_pipeline.answer_scorer import AnswerScorer
from ml_pipeline.dataset_loader import clean_sciq
from ml_pipeline.features.answer_features import expand_candidates


def test_scorer_fit_rank_save_load(tmp_path, sciq_raw_df):
    sciq = clean_sciq(sciq_raw_df, split="train")
    long = expand_candidates(sciq)
    scorer = AnswerScorer().fit(long)

    ranked = scorer.rank(
        question="What gas do plants absorb?",
        candidates=["carbon dioxide", "oxygen", "nitrogen", "argon"],
        support="Plants absorb carbon dioxide from the air during photosynthesis.",
    )
    assert len(ranked) == 4
    assert all(0.0 <= score <= 1.0 for _, score in ranked)
    assert ranked == sorted(ranked, key=lambda t: t[1], reverse=True)

    path = tmp_path / "answer_scorer.joblib"
    scorer.save(path)
    loaded = AnswerScorer.load(path)
    assert abs(
        loaded.score("What gas do plants absorb?", "carbon dioxide",
                     "Plants absorb carbon dioxide from the air.")
        - scorer.score("What gas do plants absorb?", "carbon dioxide",
                       "Plants absorb carbon dioxide from the air.")
    ) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_answer_scorer.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation** — `ml_pipeline/answer_scorer.py`

```python
"""The trained answer scorer: correct-answer vs. distractor."""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from . import config
from .features.answer_features import FeatureBuilder


class AnswerScorer:
    """Bundles a fitted TF-IDF feature builder + scaler + classifier."""

    def __init__(self, classifier=None):
        self.classifier = classifier or LogisticRegression(
            class_weight="balanced", max_iter=1000,
            random_state=config.RANDOM_SEED)
        self.feature_builder = FeatureBuilder()
        self.scaler = StandardScaler()

    def fit(self, train_long_df: pd.DataFrame) -> "AnswerScorer":
        self.feature_builder.fit(train_long_df)
        X = self.scaler.fit_transform(self.feature_builder.transform(train_long_df))
        self.classifier.fit(X, train_long_df["is_correct"].to_numpy())
        return self

    def _proba(self, X: np.ndarray) -> np.ndarray:
        if hasattr(self.classifier, "predict_proba"):
            return self.classifier.predict_proba(X)[:, 1]
        scores = self.classifier.decision_function(X)  # LinearSVC fallback
        return 1.0 / (1.0 + np.exp(-scores))

    def predict_proba(self, long_df: pd.DataFrame) -> np.ndarray:
        X = self.scaler.transform(self.feature_builder.transform(long_df))
        return self._proba(X)

    def score(self, question: str, candidate: str, support: str) -> float:
        df = pd.DataFrame([{"question": question, "candidate": candidate,
                            "support": support}])
        return float(self.predict_proba(df)[0])

    def rank(self, question, candidates, support):
        df = pd.DataFrame([{"question": question, "candidate": c,
                            "support": support} for c in candidates])
        probs = self.predict_proba(df)
        return sorted(zip(candidates, (float(p) for p in probs)),
                      key=lambda t: t[1], reverse=True)

    def save(self, path) -> None:
        config.ensure_dirs()
        joblib.dump(self, Path(path))

    @classmethod
    def load(cls, path) -> "AnswerScorer":
        return joblib.load(Path(path))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_answer_scorer.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ml_pipeline/answer_scorer.py tests/test_answer_scorer.py
git commit -m "feat(ml): AnswerScorer fit/score/rank/save/load"
```

---

## Task 9: Training bake-off, evaluation, artifacts

**Files:**
- Create: `ml_pipeline/train_models.py`
- Test: `tests/test_train_models.py`

**Interfaces:**
- Consumes: `AnswerScorer`, `expand_candidates`, `load_processed`, `config`
- Produces:
  - `evaluate(scorer, test_long_df) -> dict` — `{accuracy, f1, roc_auc, pr_auc, accuracy_at_1}`
  - `accuracy_at_1(scorer, long_df) -> float` — per-question top-1 correctness
  - `train_all(sciq_df=None, save=True) -> dict` — bake-off over LogReg/LinearSVC/RandomForest, select best by validation F1, evaluate on test, save best `AnswerScorer` to `config.MODELS_DIR/answer_scorer.joblib`, write `metrics.json`, `model_comparison.csv`, `confusion.png`, `feature_importance.png`, `model_card.json` to `config.REPORTS_DIR`. Returns metrics dict incl. `best_model` and per-model comparison.
  - `main()` — CLI entry (`python -m ml_pipeline.train_models`).

- [ ] **Step 1: Write the failing test** `tests/test_train_models.py`

```python
import pandas as pd

from ml_pipeline import config, train_models


def _toy_sciq():
    # 12 questions with a clear signal: correct answer word appears in support.
    rows = []
    for i in range(12):
        rows.append({
            "question": f"What is item {i}?",
            "correct_answer": f"alpha{i}",
            "distractor1": f"beta{i}", "distractor2": f"gamma{i}",
            "distractor3": f"delta{i}",
            "support": f"The item {i} is described as alpha{i} in the text.",
            "split": "train" if i < 8 else ("val" if i < 10 else "test"),
        })
    return pd.DataFrame(rows)


def test_accuracy_at_1_perfect_on_separable_data():
    df = _toy_sciq()
    scorer = train_models.AnswerScorer().fit(
        train_models.expand_candidates(df[df["split"] == "train"]))
    acc1 = train_models.accuracy_at_1(
        scorer, train_models.expand_candidates(df[df["split"] == "test"]))
    assert acc1 == 1.0  # correct answer is always the one present in support


def test_train_all_writes_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "reports")
    result = train_models.train_all(sciq_df=_toy_sciq(), save=True)
    assert "best_model" in result
    assert (tmp_path / "models" / "answer_scorer.joblib").exists()
    assert (tmp_path / "reports" / "metrics.json").exists()
    assert (tmp_path / "reports" / "model_comparison.csv").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_train_models.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation** — `ml_pipeline/train_models.py`

```python
"""Bake-off training + evaluation for the SciQ answer scorer."""
from __future__ import annotations

import datetime as dt
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, confusion_matrix,
                             f1_score, roc_auc_score)
from sklearn.svm import LinearSVC

from . import config
from .answer_scorer import AnswerScorer
from .features.answer_features import FeatureBuilder, expand_candidates


def _candidates():
    return {
        "logreg": LogisticRegression(class_weight="balanced", max_iter=1000,
                                     random_state=config.RANDOM_SEED),
        "linsvc": LinearSVC(class_weight="balanced",
                            random_state=config.RANDOM_SEED),
        "rf": RandomForestClassifier(n_estimators=200, max_depth=None,
                                     class_weight="balanced", n_jobs=-1,
                                     random_state=config.RANDOM_SEED),
    }


def accuracy_at_1(scorer: AnswerScorer, long_df: pd.DataFrame) -> float:
    """Per question: is the highest-scored candidate the correct one?"""
    probs = scorer.predict_proba(long_df)
    tmp = long_df.assign(_p=probs)
    hits = []
    for _, grp in tmp.groupby("question_id"):
        top = grp.loc[grp["_p"].idxmax()]
        hits.append(int(top["is_correct"] == 1))
    return float(np.mean(hits))


def evaluate(scorer: AnswerScorer, test_long: pd.DataFrame) -> dict:
    probs = scorer.predict_proba(test_long)
    preds = (probs >= 0.5).astype(int)
    y = test_long["is_correct"].to_numpy()
    return {
        "f1": float(f1_score(y, preds)),
        "roc_auc": float(roc_auc_score(y, probs)) if len(set(y)) > 1 else float("nan"),
        "pr_auc": float(average_precision_score(y, probs)) if len(set(y)) > 1 else float("nan"),
        "accuracy_at_1": accuracy_at_1(scorer, test_long),
    }


def _save_reports(best_name, best_scorer, comparison, test_long):
    config.ensure_dirs()
    (config.REPORTS_DIR / "metrics.json").write_text(
        json.dumps({"best_model": best_name, "comparison": comparison}, indent=2))
    pd.DataFrame(comparison).T.to_csv(config.REPORTS_DIR / "model_comparison.csv")

    probs = best_scorer.predict_proba(test_long)
    preds = (probs >= 0.5).astype(int)
    cm = confusion_matrix(test_long["is_correct"], preds)
    fig, ax = plt.subplots()
    ax.imshow(cm, cmap="Blues")
    for (i, j), v in np.ndenumerate(cm):
        ax.text(j, i, str(v), ha="center", va="center")
    ax.set(xlabel="predicted", ylabel="true", title=f"Confusion — {best_name}")
    fig.savefig(config.REPORTS_DIR / "confusion.png", bbox_inches="tight")
    plt.close(fig)

    clf = best_scorer.classifier
    importances = getattr(clf, "feature_importances_", None)
    if importances is None:
        importances = np.abs(np.ravel(getattr(clf, "coef_", np.zeros(len(FeatureBuilder.FEATURE_NAMES)))))
    fig, ax = plt.subplots()
    ax.barh(FeatureBuilder.FEATURE_NAMES, importances)
    ax.set_title(f"Feature importance — {best_name}")
    fig.savefig(config.REPORTS_DIR / "feature_importance.png", bbox_inches="tight")
    plt.close(fig)

    (config.REPORTS_DIR / "model_card.json").write_text(json.dumps({
        "model": best_name,
        "trained_at": dt.datetime.now().isoformat(timespec="seconds"),
        "sklearn_version": sklearn.__version__,
        "test_metrics": comparison[best_name],
        "features": FeatureBuilder.FEATURE_NAMES,
    }, indent=2))


def train_all(sciq_df: pd.DataFrame | None = None, save: bool = True) -> dict:
    if sciq_df is None:
        from .dataset_loader import load_processed
        sciq_df = load_processed("sciq")

    long = expand_candidates(sciq_df)
    train_long = long[long["split"] == "train"]
    val_long = long[long["split"] == "val"]
    test_long = long[long["split"] == "test"]

    comparison, scorers = {}, {}
    for name, clf in _candidates().items():
        scorer = AnswerScorer(classifier=clf).fit(train_long)
        scorers[name] = scorer
        eval_split = val_long if len(val_long) else test_long
        comparison[name] = evaluate(scorer, eval_split)

    best_name = max(comparison, key=lambda n: comparison[n]["f1"])
    best_scorer = scorers[best_name]
    # final, once, on test
    comparison[best_name] = evaluate(best_scorer, test_long if len(test_long) else val_long)

    if save:
        best_scorer.save(config.MODELS_DIR / "answer_scorer.joblib")
        _save_reports(best_name, best_scorer, comparison,
                      test_long if len(test_long) else val_long)

    return {"best_model": best_name, "comparison": comparison}


def main() -> None:
    result = train_all()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_train_models.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Train on the real SciQ data (verification, one-off)**

Requires Task 4 Step 5 to have produced `datasets/processed/sciq.parquet`.

Run: `.venv/bin/python -m ml_pipeline.train_models`
Expected: prints JSON with `best_model` and per-model `comparison`; **test `accuracy_at_1` should be well above 0.25** (expect ≳0.7 given the 82%-vs-4% support signal). Artifacts appear in `ml_pipeline/models/` and `ml_pipeline/reports/`.

- [ ] **Step 6: Commit**

```bash
git add ml_pipeline/train_models.py tests/test_train_models.py
git commit -m "feat(ml): answer-scorer bake-off, evaluation, artifacts"
```

---

## Task 10: retrain_from_platform + notebook_setup + README

**Files:**
- Create: `ml_pipeline/retrain_from_platform.py`, `ml_pipeline/notebook_setup.py`, `ml_pipeline/README.md`
- Test: `tests/test_retrain.py`

**Interfaces:**
- Consumes: `train_all`, `config`
- Produces:
  - `retrain_all(platform_cards=None, sciq_df=None, hierarchy_df=None, flashcards_df=None) -> dict` — calls `train_all(sciq_df=sciq_df)`, returns `{"answer_scorer": <metrics>}`. `platform_cards`/`hierarchy_df`/`flashcards_df` accepted but unused (documented; platform-feedback retraining is a later spec).
  - `bootstrap() -> None` in `notebook_setup` — inserts repo root on `sys.path`, seeds numpy/random.

- [ ] **Step 1: Write the failing test** `tests/test_retrain.py`

```python
import pandas as pd

from ml_pipeline import retrain_from_platform


def _toy_sciq():
    rows = []
    for i in range(12):
        rows.append({
            "question": f"What is item {i}?", "correct_answer": f"alpha{i}",
            "distractor1": f"beta{i}", "distractor2": f"gamma{i}",
            "distractor3": f"delta{i}",
            "support": f"Item {i} is alpha{i}.",
            "split": "train" if i < 8 else ("val" if i < 10 else "test"),
        })
    return pd.DataFrame(rows)


def test_retrain_all_returns_results(tmp_path, monkeypatch):
    from ml_pipeline import config
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "m")
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "r")
    result = retrain_from_platform.retrain_all(sciq_df=_toy_sciq())
    assert "answer_scorer" in result
    assert "best_model" in result["answer_scorer"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_retrain.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation**

`ml_pipeline/retrain_from_platform.py`:

```python
"""Retrain entry point invoked by the Django `retrain_ml_models` command.

Base retrain only: rebuilds the answer scorer from SciQ. Incorporating
platform user-performance feedback is a later spec, so `platform_cards`,
`hierarchy_df`, and `flashcards_df` are accepted but not yet used.
"""
from __future__ import annotations

from .train_models import train_all


def retrain_all(platform_cards=None, sciq_df=None, hierarchy_df=None,
                flashcards_df=None) -> dict:
    metrics = train_all(sciq_df=sciq_df)
    return {"answer_scorer": metrics}
```

`ml_pipeline/notebook_setup.py`:

```python
"""Bootstrap import paths and seeds for the pipeline notebooks."""
from __future__ import annotations

import random
import sys

import numpy as np

from . import config


def bootstrap() -> None:
    if str(config.REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(config.REPO_ROOT))
    random.seed(config.RANDOM_SEED)
    np.random.seed(config.RANDOM_SEED)
```

`ml_pipeline/README.md`:

```markdown
# StudyFlow ML Pipeline

Classical scikit-learn foundation: dataset processing, a topic hierarchy, and
a trained **answer scorer** (correct answer vs. distractor) built from SciQ.

## Setup
    .venv/bin/python -m pip install -e ".[dev]"

## Run end-to-end
    # 1. Build processed parquet from raw CSVs
    .venv/bin/python -c "from ml_pipeline.dataset_loader import build_processed_datasets as b; b()"
    # 2. Train + evaluate + save artifacts
    .venv/bin/python -m ml_pipeline.train_models

Outputs: `datasets/processed/*.parquet`, `ml_pipeline/models/answer_scorer.joblib`,
and report artifacts in `ml_pipeline/reports/`.

## Notebooks (`ml_pipeline/notebooks/`)
- `01_eda.ipynb` — dataset exploration + AI Flashcards data-quality note
- `02_preprocess.ipynb` — writes processed parquet
- `03_train_eval.ipynb` — bake-off, evaluation, artifacts

## Tests
    .venv/bin/pytest -q
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_retrain.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ml_pipeline/retrain_from_platform.py ml_pipeline/notebook_setup.py ml_pipeline/README.md tests/test_retrain.py
git commit -m "feat(ml): retrain entry point, notebook bootstrap, README"
```

---

## Task 11: Notebooks (EDA / preprocess / train-eval)

**Files:**
- Create: `ml_pipeline/notebooks/01_eda.ipynb`, `02_preprocess.ipynb`, `03_train_eval.ipynb`

**Interfaces:**
- Consumes: all pipeline modules. Notebooks are thin — each cell calls a module function.

- [ ] **Step 1: Author `02_preprocess.ipynb`**

Create a notebook (via `jupyter nbconvert`-compatible JSON or `jupytext`) whose cells are:

```python
from ml_pipeline.notebook_setup import bootstrap; bootstrap()
from ml_pipeline.dataset_loader import build_processed_datasets
paths = build_processed_datasets()
paths
```

- [ ] **Step 2: Author `01_eda.ipynb`**

Cells:

```python
from ml_pipeline.notebook_setup import bootstrap; bootstrap()
import pandas as pd
from ml_pipeline.dataset_loader import load_processed, load_raw_ai_flashcards
sciq = load_processed("sciq"); hier = load_processed("topic_hierarchy")
print("SciQ rows:", len(sciq), "| topics:", hier["topic"].nunique() if "topic" in hier else None)
```

```python
# SciQ signal: correct answer is in support far more than distractors
import numpy as np
def frac_in(col): return np.mean([str(a).lower() in str(s).lower() for a,s in zip(sciq[col], sciq["support"])])
{c: round(frac_in(c),3) for c in ["correct_answer","distractor1","distractor2","distractor3"]}
```

```python
# AI Flashcards data-quality note: difficulty is independent of features
aif = load_raw_ai_flashcards(); en = aif[aif["language"]=="en"]
pd.crosstab(en["difficulty"], en["bloom_level"], normalize="index").round(3)
```

- [ ] **Step 3: Author `03_train_eval.ipynb`**

Cells:

```python
from ml_pipeline.notebook_setup import bootstrap; bootstrap()
from ml_pipeline.train_models import train_all
result = train_all()   # trains, evaluates, saves artifacts
result["best_model"], result["comparison"][result["best_model"]]
```

```python
from IPython.display import Image
from ml_pipeline import config
Image(filename=str(config.REPORTS_DIR / "feature_importance.png"))
```

- [ ] **Step 4: Execute all notebooks headless to verify they run**

Run:
```bash
.venv/bin/jupyter nbconvert --to notebook --execute --inplace \
  ml_pipeline/notebooks/02_preprocess.ipynb \
  ml_pipeline/notebooks/01_eda.ipynb \
  ml_pipeline/notebooks/03_train_eval.ipynb
```
Expected: all three execute with no errors; `03_train_eval` prints the best model and metrics; report PNGs render.

- [ ] **Step 5: Commit**

```bash
git add ml_pipeline/notebooks/
git commit -m "feat(ml): EDA, preprocess, and train-eval notebooks"
```

---

## Task 12: Full suite + Django retrain command smoke check

**Files:** none (verification + docs)

- [ ] **Step 1: Run the whole test suite**

Run: `.venv/bin/pytest -q`
Expected: all tests PASS.

- [ ] **Step 2: Verify the Django management command imports the pipeline**

The command needs `flashcards.parquet`, `sciq.parquet`, `topic_hierarchy.parquet` (produced in Task 4) and calls `retrain_all(...)`. Run from `backend/` using the repo `.venv` with the pipeline importable:

Run:
```bash
cd backend && ../.venv/bin/python -c "import sys; sys.path.insert(0,'..'); from ml_pipeline.retrain_from_platform import retrain_all; from ml_pipeline.dataset_loader import load_processed; print(retrain_all(sciq_df=load_processed('sciq'))['answer_scorer']['best_model'])"
```
Expected: prints the best model name without error (confirms the adapter's import contract is satisfied). Note: running the actual `manage.py retrain_ml_models` also needs the `.venv` to have Django installed; if it is not, this direct import check is the authoritative contract verification for this foundation plan.

- [ ] **Step 3: Final commit (if any docs/notes changed)**

```bash
git add -A ml_pipeline docs
git commit -m "chore(ml): foundation verification pass" || echo "nothing to commit"
```

---

## Self-Review

**Spec coverage:**
- §3 integration contract → Tasks 1 (config/paths), 10 (`retrain_all` signature), 12 (import check). ✓
- §4 layout → Tasks 1–11 create every listed file. ✓
- §5.1 SciQ cleaning (splits, drop empty support) → Task 2. ✓
- §5.2 AIF cleaning + hierarchy → Task 3; parquet → Task 4. ✓
- §6.1 engineered features (leakage-safe, fit on train) → Task 7 + AnswerScorer.fit (Task 8). ✓
- §6.2 bake-off (LogReg/LinearSVC/RF, class_weight, val-selects, test-once) → Task 9. ✓
- §6.3 candidate + question-level metrics, confusion, feature importance, comparison CSV → Task 9. ✓
- §6.4 AnswerScorer persistence + model card → Tasks 8, 9. ✓
- §7 notebooks → Task 11. ✓
- §8 tests (incl. pytest install) → Tasks 1–10 each add tests; Task 12 runs all. ✓
- §9 acceptance criteria 1–7 → covered by Tasks 4/9/11/12 verification steps. ✓
- §10 AIF data-quality note → Task 11 EDA notebook. ✓

**Placeholder scan:** No TBD/TODO; every code step has complete code. ✓

**Type consistency:** `expand_candidates`, `FeatureBuilder.FEATURE_NAMES/.fit/.transform`, `AnswerScorer.fit/predict_proba/score/rank/save/load`, `train_all(sciq_df, save)`, `accuracy_at_1`, `evaluate`, `retrain_all(...)` names/signatures are consistent across Tasks 6–12 and match spec §6. ✓

**Note for implementer:** Task 4 Step 5 and Task 9 Step 5 run on the *real* datasets and are prerequisites for Task 11/12 verification; keep them in order.
