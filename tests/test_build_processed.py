from ml_pipeline import config, dataset_loader


def test_write_and_load_processed(tmp_path, monkeypatch, sciq_raw_df, aif_raw_df):
    files = {
        "sciq": tmp_path / "sciq.parquet",
        "flashcards": tmp_path / "flashcards.parquet",
        "topic_hierarchy": tmp_path / "topic_hierarchy.parquet",
    }
    monkeypatch.setattr(config, "PROCESSED_FILES", files)
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)

    sciq = dataset_loader.clean_sciq(sciq_raw_df, split="train")
    flash = dataset_loader.clean_ai_flashcards(aif_raw_df)
    hier = dataset_loader.build_topic_hierarchy(flash)

    paths = dataset_loader.write_processed(sciq, flash, hier)
    assert all(p.exists() for p in paths.values())

    reloaded = dataset_loader.load_processed("sciq")
    assert list(reloaded.columns) == list(sciq.columns)
    assert len(reloaded) == len(sciq)
