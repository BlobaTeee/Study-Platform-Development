"""Load and clean the raw datasets into tidy frames and parquet files."""
from __future__ import annotations

import glob
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd

from . import config

SCIQ_COLUMNS = [
    "question", "correct_answer", "distractor1", "distractor2",
    "distractor3", "support",
]


def _require_columns(df: pd.DataFrame, columns, dataset: str) -> None:
    """Fail loudly (and usefully) if a raw file's schema has drifted."""
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(
            f"{dataset} is missing expected column(s) {missing}. "
            f"Present columns: {list(df.columns)}. "
            "The raw data schema may have changed — see datasets/README.md."
        )


def clean_sciq(df: pd.DataFrame, split: str) -> pd.DataFrame:
    """Normalize SciQ columns, drop empty-support rows, tag the split."""
    _require_columns(df, SCIQ_COLUMNS, "SciQ")
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


AIF_KEEP_COLUMNS = [
    "subject", "topic", "subtopic", "difficulty",
    "source_text", "summary", "question", "answer",
]


def load_raw_ai_flashcards() -> pd.DataFrame:
    """Read and concatenate the AI Flashcards CSV parts (raw)."""
    paths = sorted(glob.glob(str(config.AIF_DIR / config.AIF_GLOB)))
    if not paths:
        raise FileNotFoundError(
            f"No AI Flashcards CSV parts under {config.AIF_DIR}. "
            "This raw dataset is not committed to git (137 MB); download it "
            "from the source listed in datasets/README.md. The processed "
            "outputs (flashcards.parquet, topic_hierarchy.parquet) are committed, "
            "so this is only needed to regenerate them from scratch."
        )
    return pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)


def clean_ai_flashcards(df: pd.DataFrame) -> pd.DataFrame:
    """English-only content rows, de-duplicated, content columns only."""
    _require_columns(df, AIF_KEEP_COLUMNS + ["language"], "AI Flashcards")
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


def write_processed(sciq_df, flashcards_df, hierarchy_df) -> dict:
    """Persist the three processed frames as parquet (legacy convenience)."""
    config.ensure_dirs()
    sciq_df.to_parquet(config.PROCESSED_FILES["sciq"], index=False)
    flashcards_df.to_parquet(config.PROCESSED_FILES["flashcards"], index=False)
    hierarchy_df.to_parquet(config.PROCESSED_FILES["topic_hierarchy"], index=False)
    return dict(config.PROCESSED_FILES)


# --- Dataset registry -------------------------------------------------------
# Adding a future dataset is a small, isolated change: write its build function
# and register a DatasetSpec. Datasets of kind "qa" (question / correct_answer /
# distractors / support / split) are pooled into the answer-scorer's training
# data; "guidance" datasets feed the topic hierarchy and recommendations.

# Columns a "qa" dataset must expose to join the scorer training pool.
SCORER_TRAINING_COLUMNS = SCIQ_COLUMNS + ["split"]


@dataclass(frozen=True)
class DatasetSpec:
    """Self-contained descriptor for one raw dataset.

    build:   returns the cleaned, tidy frame for this dataset.
    derived: secondary processed outputs computed from the cleaned frame,
             as ((logical_name, fn(cleaned) -> frame), ...).
    """
    name: str
    kind: str
    build: Callable[[], pd.DataFrame]
    derived: tuple[tuple[str, Callable[[pd.DataFrame], pd.DataFrame]], ...] = ()


DATASET_REGISTRY: dict[str, DatasetSpec] = {}


def register_dataset(spec: DatasetSpec) -> None:
    """Add (or replace) a dataset in the registry."""
    DATASET_REGISTRY[spec.name] = spec


def registered_datasets(kind: str | None = None) -> list[DatasetSpec]:
    """All registered specs, optionally filtered by kind."""
    return [s for s in DATASET_REGISTRY.values() if kind is None or s.kind == kind]


def processed_path(name: str) -> Path:
    """Processed parquet path for a logical dataset name."""
    return config.PROCESSED_DIR / f"{name}.parquet"


def build_processed_datasets() -> dict:
    """Full raw -> cleaned -> parquet pipeline, driven by the registry."""
    config.ensure_dirs()
    written: dict[str, Path] = {}
    for spec in DATASET_REGISTRY.values():
        cleaned = spec.build()
        path = processed_path(spec.name)
        cleaned.to_parquet(path, index=False)
        written[spec.name] = path
        for derived_name, derive in spec.derived:
            derived_path = processed_path(derived_name)
            derive(cleaned).to_parquet(derived_path, index=False)
            written[derived_name] = derived_path
    return written


def load_processed(name: str) -> pd.DataFrame:
    """Load a processed parquet by logical name."""
    path = config.PROCESSED_FILES.get(name) or processed_path(name)
    return pd.read_parquet(path)


def load_scorer_training_data() -> pd.DataFrame:
    """Pool every registered "qa" dataset into one scorer-training frame."""
    frames = []
    for spec in registered_datasets(kind="qa"):
        df = load_processed(spec.name)
        _require_columns(df, SCORER_TRAINING_COLUMNS, spec.name)
        frames.append(df[SCORER_TRAINING_COLUMNS])
    if not frames:
        raise ValueError("No 'qa' datasets registered for scorer training.")
    return pd.concat(frames, ignore_index=True)


# Built-in datasets. SciQ trains the answer scorer; AI Flashcards supplies the
# topic hierarchy (and is the "guidance" source for recommendations).
register_dataset(DatasetSpec(name="sciq", kind="qa", build=load_raw_sciq))
register_dataset(DatasetSpec(
    name="flashcards",
    kind="guidance",
    build=lambda: clean_ai_flashcards(load_raw_ai_flashcards()),
    derived=(("topic_hierarchy", build_topic_hierarchy),),
))
