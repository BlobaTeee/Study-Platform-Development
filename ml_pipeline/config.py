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
# How the answer scorer compares text: hashed character n-grams, which still
# match words the training text never had. Chosen in notebook 11.
SCORER_ANALYZER = "char"

PROCESSED_FILES = {
    "sciq": PROCESSED_DIR / "sciq.parquet",
    "flashcards": PROCESSED_DIR / "flashcards.parquet",
    "topic_hierarchy": PROCESSED_DIR / "topic_hierarchy.parquet",
}


def ensure_dirs() -> None:
    """Create output directories if missing."""
    for d in (PROCESSED_DIR, MODELS_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
