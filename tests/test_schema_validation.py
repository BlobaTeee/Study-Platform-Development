import pandas as pd
import pytest

from ml_pipeline.dataset_loader import clean_ai_flashcards, clean_sciq


def test_clean_sciq_rejects_missing_column(sciq_raw_df):
    broken = sciq_raw_df.drop(columns=["support"])
    with pytest.raises(ValueError, match="SciQ is missing expected column"):
        clean_sciq(broken, split="train")


def test_clean_aif_rejects_missing_column(aif_raw_df):
    broken = aif_raw_df.drop(columns=["language"])
    with pytest.raises(ValueError, match="AI Flashcards is missing expected column"):
        clean_ai_flashcards(broken)
