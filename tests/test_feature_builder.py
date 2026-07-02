import numpy as np

from ml_pipeline.dataset_loader import clean_sciq
from ml_pipeline.features.answer_features import FeatureBuilder, expand_candidates


def test_feature_builder_correct_beats_distractor_on_support_overlap(sciq_raw_df):
    sciq = clean_sciq(sciq_raw_df, split="train")
    long = expand_candidates(sciq)
    fb = FeatureBuilder().fit(long)
    X = fb.transform(long)
    assert X.shape == (len(long), len(FeatureBuilder.FEATURE_NAMES))
    assert not np.isnan(X).any()

    overlap = X[:, FeatureBuilder.FEATURE_NAMES.index("cand_support_overlap")]
    q0 = long["question_id"] == 0
    correct_overlap = overlap[q0.values & (long["is_correct"] == 1).values]
    distractor_overlap = overlap[q0.values & (long["is_correct"] == 0).values]
    # "carbon dioxide" is in the support; distractors are not
    assert correct_overlap.max() > distractor_overlap.max()
