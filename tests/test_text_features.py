from ml_pipeline.eda.text_features import text_stats


def test_text_stats_basic():
    s = text_stats("Cells divide. DNA replicates during mitosis.")
    assert s["n_chars"] > 0
    assert s["n_tokens"] == 6
    assert s["n_sentences"] >= 2
    assert isinstance(s["flesch_reading_ease"], float)


def test_text_stats_empty_is_safe():
    s = text_stats("")
    assert s["n_tokens"] == 0
    assert s["n_chars"] == 0
