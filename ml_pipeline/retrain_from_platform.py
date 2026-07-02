"""Retrain entry point invoked by the Django `retrain_ml_models` command.

Base retrain only: rebuilds the answer scorer from SciQ. Incorporating
platform user-performance feedback is a later spec, so `platform_cards`,
`hierarchy_df`, and `flashcards_df` are accepted but not yet used.
"""
from __future__ import annotations

from .train_models import train_all


def retrain_all(platform_cards=None, sciq_df=None, hierarchy_df=None,
                flashcards_df=None) -> dict:
    metrics = train_all(sciq_df=sciq_df)
    return {"answer_scorer": metrics}
