# ML Foundation — Design Spec

**Date:** 2026-07-03
**Status:** Approved (brainstorming) → ready for implementation plan
**Scope:** The shared ML core of the StudyFlow platform. First of several sub-project specs; feature services (flashcards, quizzes, recommendations, learning path, analytics) get their own specs later.

---

## 1. Context & Problem

StudyFlow turns a student's own study material into active-recall practice. The Django backend already has the *integration seams* for a local ML pipeline:

- [`backend/notebooks/services/generate.py`](../../../backend/notebooks/services/generate.py) calls into [`backend/ml/adapter.py`](../../../backend/ml/adapter.py), gated by a `USE_ML_PRIMARY` setting, with Gemini as the current default and a local `fallback`.
- [`backend/ml/adapter.py`](../../../backend/ml/adapter.py) imports from an `ml_pipeline` package (`ml_pipeline.services.*`, `ml_pipeline.config`, `ml_pipeline.retrain_from_platform`).
- [`retrain_ml_models`](../../../backend/ml/management/commands/retrain_ml_models.py) reads `PROCESSED_DIR / {sciq,topic_hierarchy,flashcards}.parquet`.

**But `ml_pipeline` does not exist on disk** (only a stale `egg-info` build references it), and `datasets/processed/` is empty. This spec builds the ML core that fills those slots — the "train my own ML" deliverable — with **defensible ML methodology as the primary success criterion** (Jupyter notebooks, proper splits, real evaluation metrics, report-ready artifacts). Loadable model files fall out as a byproduct.

### Datasets on hand (`datasets/raw/`)
- **AI Flashcards** — ~300k rows across 3 CSV parts. Synthetic, templated. Columns: `id, subject, topic, subtopic, difficulty, language, bloom_level, cognitive_skill, source_type, source_text, summary, question, answer, token_estimate`. Subjects: Math, CS, Physics, Biology, Chemistry. Difficulty: easy/medium/hard. Languages: en/ur/hi. **This is the classifier training data.**
- **SciQ** — ~11k real science MCQs (train/test/validation). Columns: `question, distractor1-3, correct_answer, support`. **Reserved for the later quiz/distractor feature**; processed here only so it is ready.

---

## 2. Goals & Non-Goals

### Goals
- A `ml_pipeline/` package at the repo root, matching the module names the Django adapter already imports.
- Reproducible data processing: raw CSV → cleaned, English-only, split parquet in `datasets/processed/`.
- A `subject → topic → subtopic` topic hierarchy → `topic_hierarchy.parquet`.
- Three trained + evaluated classifiers — **difficulty, subject, topic** — via a classical TF-IDF + linear/RF model bake-off, persisted with joblib.
- Jupyter notebooks (EDA + training/evaluation) and report-ready artifacts (metrics JSON, confusion-matrix PNGs, model-comparison CSVs, model cards).

### Non-Goals (deferred to later feature specs)
- The five `services/` modules (flashcard generator, quiz generator, recommendation engine, learning path). Only an empty `services/` package is created here.
- Any live wiring into the Django request path — `USE_ML_PRIMARY` stays **off**; the app keeps using Gemini until a feature spec flips it.
- Incorporating platform user-performance feedback into retraining (the `retrain_all()` here does a **base** retrain from processed datasets only).
- Deep-learning / embedding models — deliberately classical scikit-learn per the FYP framing.

---

## 3. Existing Integration Contract (honored, not changed)

The package layout and processed-file names are dictated by code that already exists:

- `ml_pipeline` must be importable from the repo root (the adapter inserts the repo root into `sys.path`).
- `ml_pipeline.config.PROCESSED_DIR` must resolve to `datasets/processed/`.
- Processed files the retrain command reads: `flashcards.parquet`, `sciq.parquet`, `topic_hierarchy.parquet`.
- `ml_pipeline.retrain_from_platform.retrain_all(platform_cards, sciq_df, hierarchy_df, flashcards_df)` must exist and return a `{name: info}` dict.

This spec fills these contracts; it does not modify the Django side.

---

## 4. Package & Artifact Layout

```
ml_pipeline/                      # repo root, importable by Django
├── __init__.py
├── config.py                    # RAW_DIR, PROCESSED_DIR, MODELS_DIR, REPORTS_DIR, RANDOM_SEED, TF-IDF & split constants
├── notebook_setup.py            # sys.path + autoreload bootstrap for notebooks
├── dataset_loader.py            # load raw CSVs; cleaning/transform fns; load processed parquet
├── eda/
│   ├── __init__.py
│   └── text_features.py         # length / readability / token features for EDA (textstat, spaCy)
├── train_models.py              # the bake-off: build pipelines, tune, evaluate, save artifacts; train_all()
├── retrain_from_platform.py     # retrain_all() — base retrain now; platform feedback deferred
├── services/
│   └── __init__.py              # empty package; feature modules land here in later specs
├── models/                      # *.joblib (Pipeline + LabelEncoder per target)   [binaries gitignored]
├── reports/                     # metrics.json, confusion_*.png, model_comparison.csv, model cards
├── notebooks/
│   ├── 01_eda.ipynb
│   ├── 02_preprocess.ipynb
│   └── 03_train_eval.ipynb
└── README.md

datasets/processed/              # flashcards.parquet, sciq.parquet, topic_hierarchy.parquet
```

`.gitignore` gains rules for `ml_pipeline/models/*.joblib` and `datasets/processed/*.parquet` (large regenerable binaries); `reports/` metric JSON/CSV and PNGs are kept (small, report evidence). Transformation logic lives in modules, not notebooks, so it is reproducible and testable; notebooks call the module functions and narrate for the report.

---

## 5. Data Pipeline

### 5.1 AI Flashcards (classifier training data)
1. Concatenate the 3 CSV parts (~300k rows).
2. **Filter to `language == 'en'`** — `ur`/`hi` rows append `[ur]`/`[hi]` markers into the text; a monolingual English study tool should not learn those. EDA reports the full language distribution **before** filtering so the choice is documented.
3. **Deduplicate** exact/near-exact `source_text` rows.
4. **Input text = `source_text`** (the honest analogue of "a chunk of a student's notes"). Targets: `difficulty`, `subject`, `topic`.
5. **Topic cardinality:** keep topics with ≥ a minimum support threshold (chosen in EDA, starting point ≥50 rows); drop rarer topics from the topic-classifier task so classes are learnable. Difficulty (3) and subject (5) used as-is after a balance check.

### 5.2 Splits & compute
- One **canonical stratified train/val/test split (70/15/15)**, stratified on `difficulty`, persisted as a `split` column in `flashcards.parquet` with fixed `RANDOM_SEED`, reused across all three targets for comparable metrics. EDA verifies subject/topic remain well-distributed across splits.
- To keep notebooks running in minutes: TF-IDF `max_features` + `min_df` caps, and RandomForest trained on a stratified subsample — all configurable in `config.py` and stated in the report.

### 5.3 SciQ (reserved)
Light processing only: normalize columns, merge train/val/test with a `split` marker, write `sciq.parquet`. Not used by the classifiers.

### 5.4 Topic hierarchy
Unique `subject → topic → subtopic` triples (with counts) from the cleaned English data → `topic_hierarchy.parquet`. Feeds later recommendation/learning-path work and the retrain command.

---

## 6. Modeling & Evaluation

### 6.1 Vectorization (leakage-safe)
TF-IDF over `source_text` — word n-grams (1–2), English stopwords, lowercase, `min_df`/`max_df`/`max_features` from `config.py`. The vectorizer lives **inside an sklearn `Pipeline(TfidfVectorizer → classifier)`** so it is refit within each CV fold and only ever sees training data (text analogue of "fit the scaler on train only"). Targets are `LabelEncoder`-encoded; the encoder is saved with each model.

### 6.2 The bake-off (per target: difficulty, subject, topic)
- **LogisticRegression**, **LinearSVC**, **RandomForest** — all `class_weight='balanced'` for class imbalance.
- Light hyperparameter tuning via `GridSearchCV`/`RandomizedSearchCV` with **cross-validation on the training set only**; the **validation split selects the winning family**; the **test split is touched exactly once** for final numbers. `RANDOM_SEED` set for numpy/sklearn.
- A `DummyClassifier` (most-frequent + stratified) baseline as a floor for context.
- LinearSVC lacks `predict_proba`; where downstream features need confidence, wrap in `CalibratedClassifierCV` or prefer LogReg — documented so probabilities are honest.

### 6.3 Evaluation artifacts (report-ready → `ml_pipeline/reports/`)
- Per-target `classification_report` (per-class + macro/weighted P/R/F1) on the **test** set; **macro-F1** is the headline metric.
- **Confusion-matrix PNGs** per target; **model-comparison CSV** (family × target → accuracy, macro-F1).
- **Top TF-IDF features per class** from linear-model coefficients — interpretability, and a visible demonstration of the subject/topic leakage caveat.
- **Train-vs-test gap** per model to show overfitting was monitored; optional keyword-ablation for subject/topic to show a realistic ceiling.

### 6.4 Persistence
Each winning `Pipeline` + its `LabelEncoder` saved via joblib to `ml_pipeline/models/` (`difficulty_clf.joblib`, `subject_clf.joblib`, `topic_clf.joblib`), each with a **model-card JSON** (train date, row count, params, test metrics, sklearn version). `train_models.py` exposes `train_all()`, callable from `03_train_eval.ipynb` and headless (`python -m ml_pipeline.train_models`); `retrain_from_platform.retrain_all()` reuses it (base retrain now; platform feedback deferred).

---

## 7. Notebooks
- **`01_eda.ipynb`** — shapes; language & class distributions; topic cardinality; `source_text` length/readability (via `eda/text_features.py` + textstat); duplicates; sample rows; subject×difficulty crosstabs. Produces report figures.
- **`02_preprocess.ipynb`** — calls cleaning functions in `dataset_loader.py`; writes `flashcards.parquet`, `sciq.parquet`, `topic_hierarchy.parquet` (+ split column).
- **`03_train_eval.ipynb`** — runs the bake-off, tuning, evaluation; saves models, model cards, and report artifacts.

All notebooks start with `notebook_setup` for path bootstrapping and reproducible seeds.

---

## 8. Testing & Reproducibility (pytest, fast — tiny fixtures, not 300k rows)
- `config` paths resolve correctly.
- `dataset_loader` cleaning on a small fixture CSV: English filter, dedup, expected schema/columns.
- Topic-hierarchy builder produces expected triples/counts on a fixture.
- **Train → save → load → predict smoke test:** a saved model loads and returns an in-vocabulary label on toy input.
- Fixed `RANDOM_SEED`; dependency versions already pinned in `pyproject.toml`.

---

## 9. Acceptance Criteria (Definition of Done)
1. `ml_pipeline/` package exists at the repo root, importable, matching the adapter's expected module names.
2. Running `02_preprocess.ipynb` (or its module functions) produces `flashcards.parquet`, `sciq.parquet`, `topic_hierarchy.parquet` in `datasets/processed/`.
3. Running `03_train_eval.ipynb` (or `python -m ml_pipeline.train_models`) trains and persists the three classifiers with model cards, and writes confusion-matrix PNGs + `model_comparison.csv` + `metrics.json` to `ml_pipeline/reports/`.
4. Each classifier **beats its DummyClassifier baseline** on macro-F1 (difficulty is the meaningful bar; subject/topic expected near-ceiling with the documented leakage caveat).
5. `retrain_from_platform.retrain_all(...)` runs against the processed datasets without error and returns a results dict, so `python manage.py retrain_ml_models` completes.
6. pytest suite (Section 8) passes.
7. `README.md` documents how to run the pipeline end-to-end.

---

## 10. Known Limitations (report-relevant, stated honestly)
- **Synthetic, templated training data.** AI Flashcards `source_text` embeds subject/topic names, so those classifiers score near-ceiling — a property of the data, not model skill. Reported explicitly, with feature-importance and optional ablation as evidence.
- **Domain shift.** Models trained on synthetic notes may not generalize to real uploaded notes; difficulty is the most transferable target. A qualitative check on a few real note snippets is included as a sanity demo.
- **Cross-dataset labels don't align** (SciQ has no difficulty/subject/topic schema), so SciQ is not a labeled eval set for these classifiers.

---

## 11. Follow-on Specs (not this spec)
1. Flashcard generation service (spaCy extraction + this difficulty classifier).
2. Quiz generation service (SciQ-backed distractors via TF-IDF similarity).
3. Recommendation engine (content-based on the topic hierarchy + performance profile).
4. Learning path / adaptive sequencing.
5. Analytics dashboard (mostly aggregation + Chart.js).
6. Live app wiring: flip `USE_ML_PRIMARY`, connect the adapter services, platform-feedback retraining.
