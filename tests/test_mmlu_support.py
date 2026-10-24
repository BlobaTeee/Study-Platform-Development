"""MMLU questions in SciQ's shape, with a Wikipedia passage as the support."""
import pandas as pd

from ml_pipeline.mmlu_support import SUBJECTS, split_of, to_sciq_shape, with_support


PASSAGE = ('SQL injection is a code injection technique used to attack data-driven applications, '
           'in which malicious SQL statements are inserted into an entry field.')


def _mmlu():
    return pd.DataFrame({
        'question': ['Which attack inserts SQL into an input field?', 'What is a break-even point?'],
        'subject': ['computer_security', 'management'],
        'choices': [['Phishing', 'SQL injection', 'Spoofing', 'Sniffing'],
                    ['Where revenue equals total cost', 'Peak profit', 'Zero sales', 'Maximum cost']],
        'answer': [1, 0],
    })


def test_rows_take_sciq_columns_with_the_answer_out_of_the_choices():
    df = to_sciq_shape(_mmlu())
    assert list(df.columns[:5]) == ['question', 'correct_answer', 'distractor1', 'distractor2', 'distractor3']
    first = df.iloc[0]
    assert first.correct_answer == 'SQL injection'
    assert {first.distractor1, first.distractor2, first.distractor3} == {'Phishing', 'Spoofing', 'Sniffing'}
    assert df.iloc[1].subject == 'management'


def test_the_split_is_by_question_and_the_same_every_run():
    assert split_of('What is a break-even point?') == split_of('What is a break-even point?')
    splits = {split_of(f'question {i}') for i in range(50)}
    assert splits == {'train', 'test'}


def test_support_comes_from_the_fetcher_and_is_cached():
    calls = []

    def fetch(query):
        calls.append(query)
        return PASSAGE

    cache = {}
    df = with_support(to_sciq_shape(_mmlu()), fetch=fetch, cache=cache)
    assert df.iloc[0].support == PASSAGE
    assert len(calls) == 2 and len(cache) == 2
    with_support(to_sciq_shape(_mmlu()), fetch=fetch, cache=cache)
    assert len(calls) == 2                       # second pass is served from the cache


def test_questions_without_a_passage_are_dropped():
    df = with_support(to_sciq_shape(_mmlu()), fetch=lambda q: '', cache={})
    assert df.empty


def test_the_seven_subjects():
    assert len(SUBJECTS) == 7 and 'computer_security' in SUBJECTS and 'marketing' in SUBJECTS


def test_a_shorter_query_is_tried_when_the_full_one_finds_nothing():
    from ml_pipeline.mmlu_support import short_query
    seen = []

    def fetch(query):
        seen.append(query)
        return PASSAGE if query == short_query('Which attack inserts SQL into an input field?', 'SQL injection') else ''

    df = with_support(to_sciq_shape(_mmlu()).iloc[:1], fetch=fetch, cache={})
    assert len(df) == 1 and len(seen) == 2


def test_the_short_query_keeps_the_content_words():
    from ml_pipeline.mmlu_support import short_query
    q = short_query('Which of the following is the best description of a buffer overflow?', 'Writing past an array end')
    assert 'buffer' in q and 'overflow' in q and 'Which' not in q and 'following' not in q
