from pathlib import Path

from ml_pipeline import config


def test_processed_dir_points_at_datasets_processed():
    assert config.PROCESSED_DIR == config.REPO_ROOT / "datasets" / "processed"
    assert config.PROCESSED_DIR.name == "processed"


def test_sciq_files_are_named_correctly():
    assert set(config.SCIQ_FILES) == {"train", "val", "test"}
    for p in config.SCIQ_FILES.values():
        assert isinstance(p, Path)


def test_ensure_dirs_creates_output_dirs(tmp_path, monkeypatch):
    for name in ("PROCESSED_DIR", "MODELS_DIR", "REPORTS_DIR"):
        monkeypatch.setattr(config, name, tmp_path / name.lower())
    config.ensure_dirs()
    for name in ("PROCESSED_DIR", "MODELS_DIR", "REPORTS_DIR"):
        assert getattr(config, name).is_dir()
