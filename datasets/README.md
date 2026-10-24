# Datasets

Data for the StudyFlow ML pipeline. This file records **provenance, licensing,
schema, and integrity** so the pipeline stays reproducible long-term.

## Layout & what is committed

```
datasets/
├── raw/                     # original source data
│   ├── SciQ/                # ✅ committed (7 MB) — the answer-scorer's training source
│   └── AI Flashcards/       # ⛔ NOT committed (137 MB) — regenerable; see below
└── processed/               # ✅ committed (5 MB) — the artifacts the pipeline consumes
    ├── sciq.parquet
    ├── flashcards.parquet
    └── topic_hierarchy.parquet
```

**Why this split:** the processed parquet the pipeline actually reads are tiny
(5 MB total) and are committed so a fresh clone can train and run immediately.
SciQ raw (7 MB) is committed for audit/regeneration. The AI Flashcards raw
(137 MB of synthetic templated text) is **kept out of git** — it is only needed
to regenerate `flashcards.parquet` / `topic_hierarchy.parquet`, which are already
committed. Model binaries (`ml_pipeline/models/*.joblib`) are regenerable and
gitignored.

## Regenerating the processed data

```bash
.venv/bin/python -c "from ml_pipeline.dataset_loader import build_processed_datasets as b; b()"
```

This needs both raw datasets present. If the AI Flashcards raw is absent, the
loader raises a clear error telling you to fetch it (below); SciQ raw is committed.

## Datasets

### SciQ  (answer-scorer training data)

- **Content:** crowdsourced multiple-choice science questions with a correct
  answer, three distractors, and a supporting passage.
- **Reference:** Welbl, Liu, Gardner (2017), *Crowdsourcing Multiple Choice
  Science Questions*; Allen Institute for AI — https://allenai.org/data/sciq
- **License:** CC BY-NC 3.0. *(Confirm against the copy you downloaded before any
  redistribution.)*
- **Official splits** (disjoint by question), row counts and SHA-256:

  | File | Rows | Size | SHA-256 |
  |------|-----:|-----:|---------|
  | `SciQ/SciQ Train Data.csv` | 11,679 | 6.4 MB | `64d8587377583e0da0648c3ccef77ac91221e67af33ed4ca00a04aaa76e133cd` |
  | `SciQ/SciQ Validation.csv` | 1,000 | 0.5 MB | `beea5c0e02797ec6f4e3ffc9a7b141fc2732f1d877f6e3a35179e335b870aee2` |
  | `SciQ/SciQ Test Data.csv` | 1,000 | 0.5 MB | `adea40a81a19660d76ed7cf9ff3fabe52a9acb7c996d4cd9ea77b9ef98111e2c` |

- **Schema:** `question, correct_answer, distractor1, distractor2, distractor3, support`
- **Cleaning:** rows with empty `support` are dropped (~10%) since the engineered
  features are support-based.

### AI Flashcards  (content + topic hierarchy only — NOT used for supervised training)

- **Content:** 300k synthetic, templated study Q/A rows with rich labels.
- **Source:** Kaggle — `bisma/ai_flashcards_notes_dataset_bisma_v1`
  (see `raw/AI Flashcards/dataset-metadata.json`).
- **License:** CC0-1.0.
- **Files** (each 100,000 rows, ~47 MB, **not committed**):

  | File | Rows | Size | SHA-256 |
  |------|-----:|-----:|---------|
  | `AI Flashcards/…v1 Part 1.csv` | 100,000 | 47.6 MB | `bafef2a38364745adc17fd438041d4525409b6daa443db5ae4396835d2fc4549` |
  | `AI Flashcards/…v1 Part 2.csv` | 100,000 | 47.8 MB | `7bc5821b4cc1edce68f496557785d858ca1c50ebf7bb0ffca0089e16abd0bb73` |
  | `AI Flashcards/…v1 Part 3.csv` | 100,000 | 47.7 MB | `6b13efed3c3479cc4a7a8ac1052c3acafdf657b2f3ae122c577d68b1927ec2af` |

- **Usage:** English rows only (100,119), de-duplicated to 67,957 → `flashcards.parquet`;
  unique subject→topic→subtopic triples (157 subtopics) → `topic_hierarchy.parquet`.
- **⚠️ Data-quality note (why its labels are not trained on):** profiling showed
  `difficulty`, `bloom_level`, and `cognitive_skill` are statistically independent
  of all features (random noise), while `subject`/`topic`/`subtopic` are written
  verbatim into `source_text` (trivial leakage; only 2,512 unique texts). See
  `docs/specs/2026-07-03-ml-foundation-design.md` §10.

### Duolingo learning traces  (memory forecast: half-life regression)

- **Source:** Settles, B. & Meeder, B. (2016). *A Trainable Spaced Repetition Model for
  Language Learning.* ACL. Data: Harvard Dataverse, doi:10.7910/DVN/N8XJME,
  file `settles.acl16.learning_traces.13m.csv.gz` (379 MB, 12.9M rows).
- **Licence:** Creative Commons Attribution-NonCommercial 4.0 (CC BY-NC 4.0). Academic,
  non-commercial use with attribution. The weights in `ml_pipeline/models/memory_hlr.json`
  derive from it and carry the same terms. The app does not use them: its forecast runs on
  FSRS-6's published parameters (MIT), see `ml_pipeline/fsrs_model.py`.
- **Committed:** ⛔ no (gitignored). Download into `datasets/raw/Duolingo/`:

  ```bash
  curl -L -o "datasets/raw/Duolingo/settles.acl16.learning_traces.13m.csv.gz" \
    "https://dataverse.harvard.edu/api/access/datafile/3091087"
  ```
- **Schema:** `p_recall` (share of a session's attempts recalled), `delta` (seconds since
  the item was last seen), `history_seen`, `history_correct`, plus user, language and
  lexeme columns the app does not use.
- **Used by:** `ml_pipeline/notebooks/08_memory_forecast.ipynb` only, an experiment that
  fits half-life regression (`ml_pipeline/memory_model.py`) and explains why the app uses
  FSRS instead.

### ProcessBench  (practice grader: first wrong step)

- **Source:** Zheng, C. et al. (2024). *ProcessBench: Identifying Process Errors in Mathematical
  Reasoning.* Qwen team. Data: Hugging Face `Qwen/ProcessBench`.
- **Licence:** Apache-2.0.
- **Committed:** ⛔ no (gitignored, 0.6 MB per split). Download into `datasets/raw/ProcessBench/`:

  ```bash
  curl -L -o datasets/raw/ProcessBench/gsm8k.json \
    "https://huggingface.co/datasets/Qwen/ProcessBench/resolve/main/gsm8k.json"
  ```
- **Schema:** `problem`, `steps` (the solution split into steps), `label` (0-based index of the
  earliest wrong step, -1 if all are right), `final_answer_correct`, `generator`.
- **Used by:** `manage.py eval_step_grading` (runs the app's practice grader, resumable) and
  `ml_pipeline/notebooks/09_step_grading.ipynb` (the metrics), via `ml_pipeline/step_grading.py`.

### Hand-made practice set  (practice grader outside maths)

- **Source:** written for this project, `datasets/handmade/practice_steps.json`.
- **What:** 24 problems in four subjects: programming and contract law (English), kinh tế and
  sinh học (Vietnamese). Each has a model solution and two more attempts, 72 in all:
  - attempts wrong on purpose, with the 0-based index of the first wrong step and its error type
    (`misread`, `concept`, `missing_step`, `execution`, `unsupported`);
  - attempts right by another route (a shortcut or a different argument), labelled -1.

  A label equal to the number of steps means the attempt stops short.
- **Labels:** set by construction, not by subject teachers. They should be reviewed, and the set
  extended by people who teach these subjects.
- **Committed:** ✅ yes (small, our own).
- **Used by:** `manage.py eval_step_grading --split handmade` and the "Outside maths" section of
  `ml_pipeline/notebooks/09_step_grading.ipynb`.

### Hand-labelled concept attachment  (knowledge map: attachment)

- **Source:** written for this project, `datasets/handmade/concept_attachment.json`.
- **What:** 81 cards, questions and practice problems of the demo account
  (`studyflow.demo@gmail.com`, three notebooks), each read against the key points of its own
  document and given the one it is about (`"<source id>:<index>"`), or `null` when none fits
  (21 items). Only documents that have key points are covered.
- **Labels:** by one person. The keys follow the stored key points: if a document is read
  again, the labels must be redone. Item texts come from `manage.py dump_concept_items`.
- **Committed:** ✅ yes (small, our own).
- **Used by:** part 2 of `ml_pipeline/notebooks/10_knowledge_map.ipynb` (`ATTACH_THRESHOLD`).

### ASSISTments 2009–2010 skill builder  (knowledge map: BKT)

- **Source:** Feng, M., Heffernan, N. & Koedinger, K. (2009). *Addressing the assessment challenge
  with an online system that tutors as it assesses.* UMUAI 19(3). Per-student sequences from the
  Hugging Face mirror `Atomi/ASSISTments2009`.
- **Licence:** free for research use with citation of the paper above.
- **Committed:** ⛔ no (gitignored). Download into `datasets/raw/ASSISTments/`:

  ```bash
  curl -L -o datasets/raw/ASSISTments/assist2009.parquet \
    "https://huggingface.co/datasets/Atomi/ASSISTments2009/resolve/main/data/train-00000-of-00001.parquet"
  ```
- **Schema:** one row per student: `skill_ids`, `skill_names`, `grades` ('1' right, '0' wrong),
  `attempt_counts`, `answer_types` (`algebra`, `choose_1`, `fill_in_1`, ...), in answer order.
- **Used by:** `ml_pipeline/notebooks/10_knowledge_map.ipynb` (fits `ml_pipeline/models/bkt.json`).

### MMLU, seven university subjects, with Wikipedia passages  (answer scorer beyond school science)

- **Source:** Hendrycks, D. et al. (2021). *Measuring Massive Multitask Language Understanding.* ICLR.
  Hugging Face `cais/mmlu`, test split of `computer_security`, `college_computer_science`,
  `machine_learning`, `business_ethics`, `management`, `marketing`, `professional_accounting`.
  Support passages: the lead of the English Wikipedia article a search for the question (then a
  shorter query) finds, through the public MediaWiki API.
- **Licence:** MMLU is MIT. Wikipedia text is CC BY-SA 4.0 (attribution: Wikipedia contributors);
  it is used only to evaluate and train the scorer and is not redistributed.
- **Committed:** ⛔ no (gitignored). Download into `datasets/raw/MMLU/`, then fetch the passages once:

  ```bash
  for s in computer_security college_computer_science machine_learning business_ethics \
           management marketing professional_accounting; do
    curl -L -o datasets/raw/MMLU/$s.parquet \
      "https://huggingface.co/datasets/cais/mmlu/resolve/main/$s/test-00000-of-00001.parquet"
  done
  .venv/bin/python -c "from ml_pipeline import mmlu_support as m; c=m.load_cache(); \
    m.with_support(m.to_sciq_shape(m.load()), cache=c); m.save_cache(c)"
  ```
- **Size:** 1,031 questions; 710 with a usable passage (333 test / 377 train, split by question).
- **Used by:** `ml_pipeline/notebooks/11_answer_scorer_domains.ipynb` (evaluation) and
  `python -m ml_pipeline.train_models` (the train half joins SciQ in the scorer's training rows).

## Integrity check

Verify a raw file has not drifted/corrupted:

```bash
shasum -a 256 "datasets/raw/SciQ/SciQ Train Data.csv"   # compare to the table above
```

The loaders (`ml_pipeline/dataset_loader.py`) also validate expected columns and
raise a clear error if a raw file's schema changes.
