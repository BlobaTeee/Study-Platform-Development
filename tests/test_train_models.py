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
    assert set(result["baselines"]) == {
        "random_at_1", "support_overlap_at_1", "dummy_f1", "dummy_roc_auc"}
    assert (tmp_path / "models" / "answer_scorer.joblib").exists()
    assert (tmp_path / "reports" / "metrics.json").exists()
    assert (tmp_path / "reports" / "model_comparison.csv").exists()


def test_train_all_defaults_to_scorer_training_pool(monkeypatch):
    # When no frame is passed, train_all pulls from the pooled "qa" datasets,
    # NOT directly from a single sciq parquet.
    from ml_pipeline import dataset_loader

    called = {"pool": False}

    def fake_pool():
        called["pool"] = True
        return _toy_sciq()

    def boom(name):  # the old path must no longer be used
        raise AssertionError(f"load_processed({name!r}) should not be called")

    monkeypatch.setattr(dataset_loader, "load_scorer_training_data", fake_pool)
    monkeypatch.setattr(dataset_loader, "load_processed", boom)

    result = train_models.train_all(save=False)

    assert called["pool"] is True
    assert "best_model" in result


def _toy_beyond():
    # University-style questions: train half only, as mmlu_support gives them.
    return pd.DataFrame([{
        "question": f"Which control blocks attack {i}?", "correct_answer": f"firewall{i}",
        "distractor1": f"router{i}", "distractor2": f"switch{i}", "distractor3": f"hub{i}",
        "support": f"A firewall{i} blocks attack {i} at the network edge.", "split": "train",
        "subject": "computer_security"} for i in range(6)])


def test_the_scorer_learns_characters_and_extra_subjects(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(train_models, "_beyond_science", _toy_beyond)
    train_models.train_all(sciq_df=_toy_sciq(), save=True, with_beyond_science=True)

    scorer = train_models.AnswerScorer.load(tmp_path / "models" / "answer_scorer.joblib")
    assert scorer.feature_builder.analyzer == config.SCORER_ANALYZER == "char"
    assert "firewall0" in "".join(scorer.rank("Which control blocks attack 0?",
                                              ["firewall0", "router0"], "A firewall0 blocks attack 0.")[0][0])


def test_without_extra_subjects_only_science_is_used(monkeypatch):
    monkeypatch.setattr(train_models, "_beyond_science", lambda: (_ for _ in ()).throw(AssertionError("not wanted")))
    result = train_models.train_all(sciq_df=_toy_sciq(), save=False)
    assert "best_model" in result
