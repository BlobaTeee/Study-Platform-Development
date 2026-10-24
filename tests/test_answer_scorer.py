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


def _science_long():
    import pandas as pd
    return pd.DataFrame({
        'question_id': [0, 0], 'question': ['What gas do plants release?'] * 2,
        'support': ['Plants release oxygen during photosynthesis.'] * 2,
        'candidate': ['oxygen', 'nitrogen'], 'is_correct': [1, 0], 'split': ['train'] * 2,
    })


def test_character_features_see_words_the_training_text_never_had():
    # Fitted on school science, a word-level vocabulary has no "injection",
    # so a security answer looks unrelated to its own source; characters do not.
    import pandas as pd
    from ml_pipeline.features.answer_features import FeatureBuilder
    probe = pd.DataFrame({'question': ['Which attack inserts code into a query?'],
                          'support': ['SQL injection inserts malicious statements into a query.'],
                          'candidate': ['SQL injection']})
    word = FeatureBuilder().fit(_science_long()).transform(probe)
    char = FeatureBuilder(analyzer='char').fit(_science_long()).transform(probe)
    assert word[0, 0] == 0.0 and char[0, 0] > 0.3


def test_a_builder_saved_before_the_option_existed_still_works():
    from ml_pipeline.features.answer_features import FeatureBuilder
    fb = FeatureBuilder().fit(_science_long())
    del fb.analyzer                       # as unpickled from an older model file
    assert fb.transform(_science_long()).shape == (2, len(FeatureBuilder.FEATURE_NAMES))
