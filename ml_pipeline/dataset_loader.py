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
