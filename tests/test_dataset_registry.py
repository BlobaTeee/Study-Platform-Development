"""Dataset registry: adding a future dataset should be a small, isolated change."""
import pytest

from ml_pipeline import config, dataset_loader as dl


@pytest.fixture
def isolated_registry(monkeypatch, tmp_path):
    """Empty registry + tmp processed dir so tests don't touch real datasets."""
    monkeypatch.setattr(dl, "DATASET_REGISTRY", {})
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp_path)
    monkeypatch.setattr(config, "PROCESSED_FILES", {})  # force processed_path fallback
    return dl.DATASET_REGISTRY


def test_builtin_registry_has_sciq_and_flashcards():
    by_name = {s.name: s for s in dl.registered_datasets()}
    assert {"sciq", "flashcards"} <= set(by_name)
    assert by_name["sciq"].kind == "qa"
    assert by_name["flashcards"].kind == "guidance"


def test_registered_datasets_filters_by_kind():
    qa_names = {s.name for s in dl.registered_datasets(kind="qa")}
    assert "sciq" in qa_names
    assert "flashcards" not in qa_names


def test_build_processed_is_registry_driven(isolated_registry, tmp_path, sciq_raw_df):
    dl.register_dataset(dl.DatasetSpec(
        name="sciq", kind="qa",
        build=lambda: dl.clean_sciq(sciq_raw_df, split="train")))

    written = dl.build_processed_datasets()

    assert (tmp_path / "sciq.parquet").exists()
    assert written["sciq"] == tmp_path / "sciq.parquet"


def test_build_processed_writes_derived_outputs(isolated_registry, tmp_path, aif_raw_df):
    dl.register_dataset(dl.DatasetSpec(
        name="flashcards", kind="guidance",
        build=lambda: dl.clean_ai_flashcards(aif_raw_df),
        derived=(("topic_hierarchy", dl.build_topic_hierarchy),)))

    written = dl.build_processed_datasets()

    assert (tmp_path / "flashcards.parquet").exists()
    assert (tmp_path / "topic_hierarchy.parquet").exists()
    assert written["topic_hierarchy"] == tmp_path / "topic_hierarchy.parquet"


def test_new_qa_dataset_joins_scorer_training_pool(isolated_registry, sciq_raw_df):
    # An existing dataset plus a newly-added one, both of kind "qa".
    dl.register_dataset(dl.DatasetSpec(
        name="sciq", kind="qa",
        build=lambda: dl.clean_sciq(sciq_raw_df, split="train")))
    dl.register_dataset(dl.DatasetSpec(
        name="extra_qa", kind="qa",
        build=lambda: dl.clean_sciq(sciq_raw_df, split="test")))
    dl.build_processed_datasets()

    pool = dl.load_scorer_training_data()

    # 2 valid rows per dataset (whitespace-support row dropped) -> 4 total.
    assert len(pool) == 4
    assert set(pool["split"]) == {"train", "test"}
    assert set(dl.SCIQ_COLUMNS + ["split"]) <= set(pool.columns)


def test_guidance_dataset_excluded_from_scorer_pool(isolated_registry, sciq_raw_df, aif_raw_df):
    dl.register_dataset(dl.DatasetSpec(
        name="sciq", kind="qa",
        build=lambda: dl.clean_sciq(sciq_raw_df, split="train")))
    dl.register_dataset(dl.DatasetSpec(
        name="flashcards", kind="guidance",
        build=lambda: dl.clean_ai_flashcards(aif_raw_df)))
    dl.build_processed_datasets()

    pool = dl.load_scorer_training_data()

    # Only the 2 valid sciq rows; the guidance dataset is not in the pool.
    assert len(pool) == 2


def test_scorer_pool_rejects_qa_dataset_missing_columns(isolated_registry, aif_raw_df):
    # A dataset mislabeled "qa" but lacking the SciQ scorer schema must fail loudly.
    dl.register_dataset(dl.DatasetSpec(
        name="bad_qa", kind="qa",
        build=lambda: dl.clean_ai_flashcards(aif_raw_df)))
    dl.build_processed_datasets()

    with pytest.raises(ValueError, match="missing expected column"):
        dl.load_scorer_training_data()
