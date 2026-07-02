from ml_pipeline.dataset_loader import clean_sciq
from ml_pipeline.features.answer_features import expand_candidates


def test_expand_candidates_shape_and_labels(sciq_raw_df):
    sciq = clean_sciq(sciq_raw_df, split="train")  # 2 questions survive
    long = expand_candidates(sciq)
    assert len(long) == len(sciq) * 4
    assert set(long.columns) == {
        "question_id", "question", "candidate", "support", "split", "is_correct",
    }
    # exactly one correct per question
    per_q = long.groupby("question_id")["is_correct"].sum()
    assert (per_q == 1).all()
    # correct candidate matches the source correct_answer
    first = long[long["question_id"] == long["question_id"].iloc[0]]
    correct = first[first["is_correct"] == 1]["candidate"].iloc[0]
    assert correct == sciq["correct_answer"].iloc[0]
