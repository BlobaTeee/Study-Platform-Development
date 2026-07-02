"""Expand SciQ rows into (question, candidate) examples and build features."""
from __future__ import annotations

import numpy as np
import pandas as pd

_DISTRACTORS = ["distractor1", "distractor2", "distractor3"]


def expand_candidates(sciq_df: pd.DataFrame) -> pd.DataFrame:
    """One row per candidate answer; is_correct=1 for the correct answer."""
    records = []
    for qid, row in enumerate(sciq_df.itertuples(index=False)):
        base = {"question_id": qid, "question": row.question,
                "support": row.support, "split": row.split}
        records.append({**base, "candidate": row.correct_answer, "is_correct": 1})
        for col in _DISTRACTORS:
            records.append({**base, "candidate": getattr(row, col), "is_correct": 0})
    return pd.DataFrame.from_records(records)
