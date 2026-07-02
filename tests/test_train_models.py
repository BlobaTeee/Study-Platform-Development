import pandas as pd

from ml_pipeline import config, train_models


def _toy_sciq():
    # 12 questions with a clear signal: correct answer word appears in support.
    rows = []
    for i in range(12):
        rows.append({
            "question": f"What is item {i}?",
            "correct_answer": f"alpha{i}",
            "distractor1": f"beta{i}", "distractor2": f"gamma{i}",
            "distractor3": f"delta{i}",
            "support": f"The item {i} is described as alpha{i} in the text.",
            "split": "train" if i < 8 else ("val" if i < 10 else "test"),
        })
    return pd.DataFrame(rows)


def test_accuracy_at_1_perfect_on_separable_data():
    df = _toy_sciq()
    scorer = train_models.AnswerScorer().fit(
        train_models.expand_candidates(df[df["split"] == "train"]))
    acc1 = train_models.accuracy_at_1(
        scorer, train_models.expand_candidates(df[df["split"] == "test"]))
    assert acc1 == 1.0  # correct answer is always the one present in support


def test_train_all_writes_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "reports")
    result = train_models.train_all(sciq_df=_toy_sciq(), save=True)
    assert "best_model" in result
    assert (tmp_path / "models" / "answer_scorer.joblib").exists()
    assert (tmp_path / "reports" / "metrics.json").exists()
    assert (tmp_path / "reports" / "model_comparison.csv").exists()
