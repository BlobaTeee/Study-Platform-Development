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
