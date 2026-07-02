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

## Integrity check

Verify a raw file has not drifted/corrupted:

```bash
shasum -a 256 "datasets/raw/SciQ/SciQ Train Data.csv"   # compare to the table above
```

The loaders (`ml_pipeline/dataset_loader.py`) also validate expected columns and
raise a clear error if a raw file's schema changes.
