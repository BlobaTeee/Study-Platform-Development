from ml_pipeline.answer_scorer import AnswerScorer
from ml_pipeline.dataset_loader import clean_sciq
from ml_pipeline.features.answer_features import expand_candidates


def test_scorer_fit_rank_save_load(tmp_path, sciq_raw_df):
    sciq = clean_sciq(sciq_raw_df, split="train")
    long = expand_candidates(sciq)
    scorer = AnswerScorer().fit(long)

    ranked = scorer.rank(
        question="What gas do plants absorb?",
        candidates=["carbon dioxide", "oxygen", "nitrogen", "argon"],
        support="Plants absorb carbon dioxide from the air during photosynthesis.",
    )
    assert len(ranked) == 4
    assert all(0.0 <= score <= 1.0 for _, score in ranked)
    assert ranked == sorted(ranked, key=lambda t: t[1], reverse=True)

    path = tmp_path / "answer_scorer.joblib"
    scorer.save(path)
    loaded = AnswerScorer.load(path)
    assert abs(
        loaded.score("What gas do plants absorb?", "carbon dioxide",
                     "Plants absorb carbon dioxide from the air.")
        - scorer.score("What gas do plants absorb?", "carbon dioxide",
                       "Plants absorb carbon dioxide from the air.")
    ) < 1e-9
