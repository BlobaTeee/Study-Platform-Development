import pandas as pd

from ml_pipeline import retrain_from_platform


def _toy_sciq():
    rows = []
    for i in range(12):
        rows.append({
            "question": f"What is item {i}?", "correct_answer": f"alpha{i}",
            "distractor1": f"beta{i}", "distractor2": f"gamma{i}",
            "distractor3": f"delta{i}",
            "support": f"Item {i} is alpha{i}.",
            "split": "train" if i < 8 else ("val" if i < 10 else "test"),
        })
    return pd.DataFrame(rows)


def test_retrain_all_returns_results(tmp_path, monkeypatch):
    from ml_pipeline import config
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "m")
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "r")
    result = retrain_from_platform.retrain_all(sciq_df=_toy_sciq())
    assert "answer_scorer" in result
    assert "best_model" in result["answer_scorer"]
