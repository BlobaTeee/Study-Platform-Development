# ML Foundation — Design Spec

**Date:** 2026-07-03
**Status:** Approved (brainstorming) → ready for implementation plan
**Scope:** The shared ML core of the StudyFlow platform. First of several sub-project specs; feature services (flashcards, quizzes, recommendations, learning path, analytics) get their own specs later.

> **Revision note (2026-07-03):** The original draft planned three text classifiers (difficulty/subject/topic) on the AI Flashcards dataset. Data profiling **before implementation** showed that dataset cannot support a defensible supervised classifier: `difficulty`, `bloom_level`, and `cognitive_skill` are **random noise** (statistically independent of every feature — same questions/subtopics appear under all labels), while `subject`/`topic` are **trivially leaked** (the label name is written verbatim into `source_text`, and only 2,512 unique `source_text` strings exist). The foundation's trained model was therefore pivoted to a **SciQ correct-vs-distractor answer scorer** — a genuinely learnable task on real data that also front-loads the ML behind the later quiz feature. The AIF findings are retained as a short data-quality note (§10), not a full case study.

---

## 1. Context & Problem

StudyFlow turns a student's own study material into active-recall practice. The Django backend already has the *integration seams* for a local ML pipeline:

- [`backend/notebooks/services/generate.py`](../../../backend/notebooks/services/generate.py) calls into [`backend/ml/adapter.py`](../../../backend/ml/adapter.py), gated by a `USE_ML_PRIMARY` setting, with Gemini as the current default and a local `fallback`.
- [`backend/ml/adapter.py`](../../../backend/ml/adapter.py) imports from an `ml_pipeline` package (`ml_pipeline.services.*`, `ml_pipeline.config`, `ml_pipeline.retrain_from_platform`).
- [`retrain_ml_models`](../../../backend/ml/management/commands/retrain_ml_models.py) reads `PROCESSED_DIR / {sciq,topic_hierarchy,flashcards}.parquet`.

**But `ml_pipeline` does not exist on disk** (only a stale `egg-info` build references it), and `datasets/processed/` is empty. This spec builds the ML core that fills those slots — the "train my own ML" deliverable — with **defensible ML methodology as the primary success criterion** (Jupyter notebooks, proper splits, real evaluation metrics, report-ready artifacts). A loadable model file falls out as a byproduct.

### Datasets on hand (`datasets/raw/`)
- **SciQ** — real crowdsourced science MCQs. Official splits: **train 11,679 / validation 1,000 / test 1,000**, disjoint by question. Columns: `question, distractor1, distractor2, distractor3, correct_answer, support`. The correct answer is a substring of `support` **82%** of the time vs. **4%** for distractors — strong, real, non-trivial signal (18% of correct answers are *not* literally in support). ~10% of rows have empty `support`. **This is the classifier training data.**
- **AI Flashcards** — ~300k synthetic, templated rows (100,119 English) with rich labels. **Not suitable for supervised classification** (see Revision note / §10), but a useful source of Q/A content and a `subject→topic→subtopic` hierarchy for later features. Processed here as content + hierarchy only.

---

## 2. Goals & Non-Goals

### Goals
- A `ml_pipeline/` package at the repo root, matching the module names the Django adapter already imports.
- Reproducible data processing: raw CSV → cleaned parquet in `datasets/processed/` (`sciq.parquet`, `flashcards.parquet`, `topic_hierarchy.parquet`).
- A trained + evaluated **answer scorer**: a binary classifier that, given `(question, candidate_answer, support)`, predicts correct vs. distractor — via engineered similarity/overlap features and a classical model bake-off. Persisted with joblib.
- A `subject → topic → subtopic` topic hierarchy from AI Flashcards → `topic_hierarchy.parquet` (feeds later recommendation/learning-path).
- Jupyter notebooks (EDA + preprocess + training/evaluation) and report-ready artifacts (metrics JSON, confusion-matrix + feature-importance PNGs, model-comparison CSV, model card).

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
├── config.py                    # RAW_DIR, PROCESSED_DIR, MODELS_DIR, REPORTS_DIR, RANDOM_SEED, TF-IDF constants
├── notebook_setup.py            # sys.path + autoreload bootstrap for notebooks
├── dataset_loader.py            # load raw CSVs; SciQ + AIF cleaning fns; load processed parquet
├── eda/
│   ├── __init__.py
│   └── text_features.py         # length / readability / token features for EDA (textstat, spaCy)
├── features/
│   ├── __init__.py
│   └── answer_features.py       # expand SciQ→candidates; build engineered feature matrix
├── answer_scorer.py             # AnswerScorer: fit/save/load, score(), rank() — bundles vectorizer+scaler+clf
├── train_models.py              # the bake-off: train candidates, tune, evaluate, save artifacts; train_all()
├── retrain_from_platform.py     # retrain_all() — base retrain of answer scorer; platform feedback deferred
├── services/
│   └── __init__.py              # empty package; feature modules land here in later specs
├── models/                      # answer_scorer.joblib   [binaries gitignored]
├── reports/                     # metrics.json, confusion.png, feature_importance.png, model_comparison.csv, model_card.json
├── notebooks/
│   ├── 01_eda.ipynb
│   ├── 02_preprocess.ipynb
│   └── 03_train_eval.ipynb
└── README.md

datasets/processed/              # sciq.parquet, flashcards.parquet, topic_hierarchy.parquet
```

`.gitignore` gains rules for `ml_pipeline/models/*.joblib` and `datasets/processed/*.parquet` (large regenerable binaries); `reports/` metric JSON/CSV and PNGs are kept (small, report evidence). Transformation and feature logic lives in modules, not notebooks, so it is reproducible and testable; notebooks call the module functions and narrate for the report.

---

## 5. Data Pipeline

### 5.1 SciQ (classifier training data)
1. Load official train/val/test CSVs; attach a `split` column (`train`/`val`/`test`) — **respect the official splits** (they are disjoint by question, preventing group leakage).
2. **Drop rows with empty/whitespace `support`** (~10%): the engineered features are support-based, so blank support would inject meaningless zeros. Count dropped rows reported in EDA.
3. Normalize columns to `question, correct_answer, distractor1, distractor2, distractor3, support, split`; write `sciq.parquet` (row-level, one row per question).
4. **Candidate expansion (at train time, in `features/answer_features.py`):** each SciQ row → 4 examples `(question, candidate, support, split, is_correct)` — 1 positive (correct_answer) + 3 negatives (distractors). ~25% positive → handled with `class_weight='balanced'`. Expansion keeps a `question_id` so question-level metrics can group candidates.

### 5.2 AI Flashcards (content + hierarchy only — not for classification)
1. Concatenate the 3 CSV parts; **filter to `language == 'en'`** (100,119 rows).
2. Deduplicate full duplicate rows; keep `subject, topic, subtopic, difficulty, source_text, summary, question, answer` columns; write `flashcards.parquet` (content store for the later flashcard feature).
3. **Topic hierarchy:** unique `subject → topic → subtopic` triples (with counts) → `topic_hierarchy.parquet` (5 subjects, 20 topics, 157 subtopics).
4. No classifier is trained on this data — see §10 for the documented reason.

---

## 6. Modeling & Evaluation (the trained ML deliverable)

### 6.1 Engineered features (leakage-safe) — `features/answer_features.py`
Per `(question, candidate, support)` example, build a **dense** feature vector:
- `cand_support_cos` — TF-IDF cosine similarity between candidate and support.
- `cand_question_cos` — TF-IDF cosine similarity between candidate and question.
- `cand_support_overlap` — fraction of candidate tokens present in support.
- `cand_question_overlap` — fraction of candidate tokens present in question.
- `cand_len_tokens`, `cand_len_chars`, `cand_is_numeric` (candidate is numeric/units).
- `support_len_tokens`.

The TF-IDF vectorizer is fit on **train support+questions only**; the `StandardScaler` is fit on **train features only** (both applied to val/test) — the leakage rule from ml-model-training. Vectorizer + scaler are bundled into the saved artifact.

### 6.2 The bake-off (binary: correct vs. distractor)
- **LogisticRegression**, **LinearSVC**, **RandomForest** — all `class_weight='balanced'`.
- Light hyperparameter tuning via `GridSearchCV`/`RandomizedSearchCV` with CV on **train only**; the **val split selects the winning family**; the **test split is scored exactly once**. `RANDOM_SEED` fixed.
- **Two baselines** for context: `DummyClassifier` (stratified) and a heuristic "highest `cand_support_overlap` wins" rule.

### 6.3 Evaluation artifacts (report-ready → `ml_pipeline/reports/`)
- **Candidate-level:** accuracy, precision/recall/F1 (positive = correct), ROC-AUC, PR-AUC; confusion matrix PNG.
- **Question-level (headline, product-relevant):** **answer-selection accuracy@1** — for each question, rank its 4 candidates by model score; is the top-ranked one the correct answer? (Chance = 25%.) Reported for the model and both baselines.
- **Feature importances** (LogReg coefficients / RF importances) PNG + table — expected to show support-overlap dominating; strong interpretability story.
- **Train-vs-test gap** per model to show overfitting was monitored; **model-comparison CSV** (family × metric).

### 6.4 Persistence — `answer_scorer.py`
An `AnswerScorer` class bundles the fitted TF-IDF vectorizer + `StandardScaler` + winning classifier and exposes:
- `AnswerScorer.fit(train_df) -> AnswerScorer`
- `.score(question, candidate, support) -> float` (P(correct))
- `.rank(question, candidates, support) -> list[(candidate, score)]` sorted desc
- `.save(path)` / `AnswerScorer.load(path)` (joblib)

Saved to `ml_pipeline/models/answer_scorer.joblib` with a **model-card JSON** (train date, row counts, params, test metrics, sklearn version). `train_models.train_all()` trains + evaluates + saves; callable from `03_train_eval.ipynb` and headless (`python -m ml_pipeline.train_models`). `retrain_from_platform.retrain_all(...)` reuses it (base retrain from `sciq_df`; platform feedback deferred).

---

## 7. Notebooks
- **`01_eda.ipynb`** — SciQ: support coverage, answer/distractor length, the substring-in-support signal (82% vs 4%), candidate class balance; brief AIF data-quality note (§10) with the leakage/noise crosstabs; topic-hierarchy overview. Produces report figures.
- **`02_preprocess.ipynb`** — calls cleaning functions in `dataset_loader.py`; writes `sciq.parquet`, `flashcards.parquet`, `topic_hierarchy.parquet`.
- **`03_train_eval.ipynb`** — expands candidates, builds features, runs the bake-off + tuning, computes candidate- and question-level metrics, saves the model, model card, and report artifacts.

All notebooks start with `notebook_setup` for path bootstrapping and reproducible seeds.

---

## 8. Testing & Reproducibility (pytest, fast — tiny fixtures, not full datasets)
- Add `pytest` to dev dependencies (the repo `.venv` lacks it).
- `config` paths resolve correctly.
- `dataset_loader` SciQ cleaning on a small fixture: empty-support rows dropped, expected columns, split markers preserved.
- `dataset_loader` AIF cleaning: English filter, dedup.
- Topic-hierarchy builder produces expected triples/counts on a fixture.
- `features/answer_features` correctness: on a crafted example, the correct answer (present in support) yields a higher `cand_support_overlap`/`cand_support_cos` than a distractor absent from support; candidate expansion yields 4 rows with exactly one positive.
- **Train → save → load → rank smoke test:** `AnswerScorer.fit` on a tiny fixture, save, load, and `.rank()` returns all candidates ordered with valid scores in [0,1].
- Fixed `RANDOM_SEED`; dependency versions already pinned in `pyproject.toml`.

---

## 9. Acceptance Criteria (Definition of Done)
1. `ml_pipeline/` package exists at the repo root, importable, matching the adapter's expected module names.
2. Running `02_preprocess.ipynb` (or its module functions) produces `sciq.parquet`, `flashcards.parquet`, `topic_hierarchy.parquet` in `datasets/processed/`.
3. Running `03_train_eval.ipynb` (or `python -m ml_pipeline.train_models`) trains and persists `answer_scorer.joblib` + model card, and writes `confusion.png`, `feature_importance.png`, `model_comparison.csv`, `metrics.json` to `ml_pipeline/reports/`.
4. The trained answer scorer **beats both baselines** (Dummy and support-overlap-only) on candidate-level ROC-AUC/macro-F1, and achieves **question-level answer-selection accuracy@1 well above the 25% chance level** on the held-out test split — the real, defensible result.
5. `retrain_from_platform.retrain_all(...)` runs against the processed datasets without error and returns a results dict, so `python manage.py retrain_ml_models` completes.
6. pytest suite (Section 8) passes.
7. `README.md` documents how to run the pipeline end-to-end.

---

## 10. Known Limitations & Data-Quality Note (report-relevant, stated honestly)
- **Why not the AI Flashcards labels?** Profiling the 100,119 English rows showed the labels are unusable for supervised learning: `difficulty`, `bloom_level`, and `cognitive_skill` are **statistically independent of all features** (identical `token_estimate` means; uniform crosstabs; the same 628 questions and 157 subtopics appear under every label) — i.e., random noise; while `subject`/`topic`/`subtopic` are **written verbatim into `source_text`** with only 2,512 unique texts, making any classifier a trivial template lookup. This is a property of the synthetic generator, documented with crosstab/feature-importance evidence in EDA. The dataset is retained for Q/A content and the topic hierarchy.
- **SciQ scope.** SciQ is science-only, so the answer scorer's learned signal (answer-in-support overlap, question-answer similarity) is domain-general in mechanism but trained on science text; generalization to other subjects is noted as future work.
- **Empty-support rows dropped (~10%)** from the answer-scorer study, so the model assumes a support passage is available; the later quiz feature will supply the student's own source text as "support."

---

## 11. Follow-on Specs (not this spec)
1. Quiz generation service (SciQ-backed distractor selection + this answer scorer to validate correct answers / rank distractors).
2. Flashcard generation service (spaCy extraction over the student's notes; `flashcards.parquet` as content reference).
3. Recommendation engine (content-based on the topic hierarchy + performance profile).
4. Learning path / adaptive sequencing.
5. Analytics dashboard (mostly aggregation + Chart.js).
6. Live app wiring: flip `USE_ML_PRIMARY`, connect the adapter services, platform-feedback retraining.
