# StudyFlow ML Pipeline

Classical scikit-learn foundation: dataset processing, a topic hierarchy, and
a trained **answer scorer** (correct answer vs. distractor) built from SciQ.

## Setup

    .venv/bin/python -m pip install -e ".[dev]"

(The repo `.venv` already has the ML stack; this adds `pytest`.)

## Run end-to-end

    # 1. Build processed parquet from raw CSVs
    .venv/bin/python -c "from ml_pipeline.dataset_loader import build_processed_datasets as b; b()"
    # 2. Train + evaluate + save artifacts
    .venv/bin/python -m ml_pipeline.train_models

Outputs: `datasets/processed/*.parquet`, `ml_pipeline/models/answer_scorer.joblib`,
and report artifacts in `ml_pipeline/reports/` (metrics, confusion matrix,
feature importances, model comparison, model card).

## The answer scorer

`AnswerScorer` bundles a fitted TF-IDF feature builder + `StandardScaler` + a
classifier chosen by a validation bake-off (LogReg / LinearSVC / RandomForest),
selected on the held-out **accuracy@1** metric. Usage:

```python
from ml_pipeline.answer_scorer import AnswerScorer
from ml_pipeline import config
scorer = AnswerScorer.load(config.MODELS_DIR / "answer_scorer.joblib")
scorer.rank("What gas do plants absorb?",
            ["carbon dioxide", "oxygen", "nitrogen", "argon"],
            support="Plants absorb carbon dioxide during photosynthesis.")
```

## Notebooks (`ml_pipeline/notebooks/`)

- `01_eda.ipynb` — dataset exploration + AI Flashcards data-quality note
- `02_preprocess.ipynb` — writes processed parquet
- `03_train_eval.ipynb` — bake-off, evaluation, artifacts

## Tests

    .venv/bin/pytest -q
