from ml_pipeline.dataset_loader import build_topic_hierarchy, clean_ai_flashcards


def test_clean_aif_english_only_and_dedup(aif_raw_df):
    out = clean_ai_flashcards(aif_raw_df)
    # 4 raw rows: 2 identical en (->1), 1 ur (dropped), 1 distinct en -> total 2
    assert len(out) == 2
    assert set(out.columns) == {
        "subject", "topic", "subtopic", "difficulty",
        "source_text", "summary", "question", "answer",
    }
    assert "language" not in out.columns


def test_build_topic_hierarchy_counts_triples(aif_raw_df):
    cleaned = clean_ai_flashcards(aif_raw_df)
    hier = build_topic_hierarchy(cleaned)
    assert set(hier.columns) == {"subject", "topic", "subtopic", "count"}
    assert len(hier) == 2  # Continuity + Limits
    assert hier["count"].sum() == len(cleaned)
