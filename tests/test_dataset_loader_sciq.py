from ml_pipeline.dataset_loader import clean_sciq


def test_clean_sciq_drops_empty_support_and_tags_split(sciq_raw_df):
    out = clean_sciq(sciq_raw_df, split="train")
    assert len(out) == 2  # the whitespace-support row is dropped
    assert set(out.columns) == {
        "question", "correct_answer", "distractor1", "distractor2",
        "distractor3", "support", "split",
    }
    assert (out["split"] == "train").all()
    assert out["support"].str.strip().astype(bool).all()
