from ml_pipeline.services.topic_index import TopicIndex, TopicRow


def test_from_frames_builds_rows_with_difficulty(guidance_hierarchy_df, guidance_flashcards_df):
    idx = TopicIndex.from_frames(guidance_hierarchy_df, guidance_flashcards_df)
    rows = idx.rows_for_subject("Mathematics")
    assert {r.subtopic for r in rows} == {"Continuity", "Limits", "Polynomials"}
    # difficulty aggregated from flashcards (majority vote)
    assert idx.difficulty_for("Mathematics", "Calculus", "Continuity") == "hard"
    assert idx.difficulty_for("Mathematics", "Calculus", "Limits") == "easy"


def test_missing_difficulty_defaults_to_medium(guidance_hierarchy_df):
    import pandas as pd
    idx = TopicIndex.from_frames(guidance_hierarchy_df, pd.DataFrame())
    assert idx.difficulty_for("Physics", "Mechanics", "Kinematics") == "medium"


def test_search_ranks_relevant_subtopic_first(guidance_hierarchy_df, guidance_flashcards_df):
    idx = TopicIndex.from_frames(guidance_hierarchy_df, guidance_flashcards_df)
    hits = idx.search("continuity of a function", n=3)
    assert hits, "expected at least one hit"
    top_row, top_score = hits[0]
    assert top_row.subtopic == "Continuity"
    assert top_score > 0


def test_search_empty_text_returns_empty(guidance_hierarchy_df, guidance_flashcards_df):
    idx = TopicIndex.from_frames(guidance_hierarchy_df, guidance_flashcards_df)
    assert idx.search("", n=5) == []


def test_top_by_coverage_orders_by_count(guidance_hierarchy_df, guidance_flashcards_df):
    idx = TopicIndex.from_frames(guidance_hierarchy_df, guidance_flashcards_df)
    top = idx.top_by_coverage(2)
    assert [r.subtopic for r in top] == ["Limits", "Kinematics"]  # counts 50, 40


def test_default_subject_is_highest_total_coverage(guidance_hierarchy_df, guidance_flashcards_df):
    idx = TopicIndex.from_frames(guidance_hierarchy_df, guidance_flashcards_df)
    # Mathematics total = 100, Physics = 40
    assert idx.default_subject() == "Mathematics"
