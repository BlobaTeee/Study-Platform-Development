"""Chấm chất lượng câu hỏi trắc nghiệm: đo "câu hỏi có đúng không",
không phải "đáp án có chép lại chữ trong tài liệu không"."""
from ml_pipeline.question_quality import (
    is_negative_question, score_question, score_set, support,
)

EXCERPT = (
    "Mobile phones function simultaneously as a lifeline and as a source of risk. "
    "They let young people summon help in emergencies, remain in contact with trusted "
    "others and manage dangerous situations. Phone theft, loss, damage, depleted "
    "batteries and the cost of service repeatedly undermine that safety benefit."
)


# ---- support: khẳng định của tài liệu, không đòi trùng từng chữ ----------------------

def test_a_paraphrase_still_counts_as_supported():
    assert support("phones are both a lifeline and a source of risk", EXCERPT) > 0.5


def test_something_the_excerpt_never_says_is_not_supported():
    assert support("lack of storage space", EXCERPT) < 0.3


def test_an_exact_quote_is_supported():
    assert support("depleted batteries", EXCERPT) > 0.8


# ---- lỗi thật của model nhỏ: một phương án nhiễu cũng đúng ---------------------------

def test_a_distractor_the_excerpt_also_supports_is_flagged():
    # Đây chính là câu llama3.2:3b sinh ra: đáp án "a source of risk" nhưng
    # nhiễu "a lifeline" cũng đúng theo tài liệu.
    report = score_question(
        {'question_text': 'What role do mobile phones play in personal safety?',
         'correct_answer': 'a source of risk',
         'distractors': ['a lifeline', 'a way to pay rent', 'a school requirement']},
        EXCERPT,
    )
    assert 'rival_distractor' in report.flags
    assert report.rivals == ['a lifeline']
    assert report.ok is False


def test_a_question_whose_distractors_are_all_wrong_passes():
    report = score_question(
        {'question_text': 'What do phones let young people do in an emergency?',
         'correct_answer': 'summon help',
         'distractors': ['pay their rent', 'find a landlord', 'renew a passport']},
        EXCERPT,
    )
    assert report.flags == [] and report.ok is True


# ---- câu dạng phủ định: phép kiểm phải lật ngược ------------------------------------

def test_a_negative_question_is_recognised_in_both_languages():
    assert is_negative_question('Which of the following is NOT listed as a factor?')
    assert is_negative_question('Điều nào sau đây KHÔNG được nêu trong đoạn?')
    assert is_negative_question('Tất cả đều đúng, ngoại trừ?')
    assert not is_negative_question('Điện thoại giúp gì cho người trẻ vô gia cư?')


def test_a_good_negative_question_is_not_punished_for_its_answer():
    # Đáp án đúng cố tình KHÔNG có trong tài liệu; ba nhiễu thì có.
    report = score_question(
        {'question_text': 'Which of the following is NOT listed as undermining the benefit?',
         'correct_answer': 'lack of storage space',
         'distractors': ['phone theft', 'depleted batteries', 'the cost of service']},
        EXCERPT,
    )
    assert report.flags == [] and report.ok is True


def test_a_broken_negative_question_is_caught():
    # Đáp án "đúng" lại là thứ tài liệu có nói → câu hỏi sai.
    report = score_question(
        {'question_text': 'Which of these is NOT mentioned?',
         'correct_answer': 'phone theft',
         'distractors': ['buying a car', 'joining a gym', 'paying tuition']},
        EXCERPT,
    )
    assert 'answer_unsupported' not in report.flags
    assert 'negative_answer_supported' in report.flags and report.ok is False


# ---- nhiễu nhại lại đáp án ----------------------------------------------------------

def test_a_distractor_that_echoes_the_answer_is_flagged():
    report = score_question(
        {'question_text': 'What undermines the safety benefit?',
         'correct_answer': 'phone theft',
         'distractors': ['theft of the phone', 'a new battery brand', 'a cheaper plan']},
        EXCERPT,
    )
    assert 'distractor_echoes_answer' in report.flags


# ---- đáp án không được tài liệu khẳng định ------------------------------------------

def test_an_invented_answer_is_flagged():
    report = score_question(
        {'question_text': 'How many young people were interviewed?',
         'correct_answer': 'forty-two',
         'distractors': ['ten', 'twenty', 'sixty']},
        EXCERPT,
    )
    assert 'answer_unsupported' in report.flags and report.ok is False


# ---- cả bộ: trùng lặp và bảng điểm --------------------------------------------------

def test_a_set_reports_duplicates_and_a_pass_rate():
    items = [
        {'question_text': 'What do phones let young people do in an emergency?',
         'correct_answer': 'summon help', 'distractors': ['pay rent', 'find a landlord', 'renew a passport']},
        {'question_text': 'What do phones let young people do in an emergency?',
         'correct_answer': 'summon help', 'distractors': ['pay rent', 'find a landlord', 'renew a passport']},
        {'question_text': 'What role do mobile phones play in personal safety?',
         'correct_answer': 'a source of risk', 'distractors': ['a lifeline', 'a car', 'a job']},
    ]

    card = score_set(items, EXCERPT)

    assert card['total'] == 3
    assert card['duplicates'] == 1
    assert card['passed'] == 1                    # câu trùng bị loại, câu nhiễu-cũng-đúng trượt
    assert 0.3 <= card['pass_rate'] <= 0.4
    assert card['flag_counts']['rival_distractor'] == 1


# ---- nhiễu lấy từ chỗ khác trong tài liệu là nhiễu TỐT, không phải lỗi ---------------

MULTI_TOPIC = (
    "In healthcare, AI raises questions of data governance and patient privacy. "
    "For self-driving cars, the ethical issues highlighted are liability in a crash "
    "and how the vehicle should decide between harms. "
    "Australia has published a voluntary AI ethics framework. "
    "The European Union plans to contribute at least 14 billion euros to AI investment."
)


def test_a_distractor_true_elsewhere_in_the_document_is_not_a_rival():
    # Gemini sinh câu này. "Data governance and patient privacy" có trong tài liệu,
    # nhưng ở đoạn nói về y tế — nên với câu hỏi về xe tự lái nó sai, và đó đúng là
    # một nhiễu hay.
    report = score_question(
        {'question_text': 'What are the specific ethical issues highlighted for self-driving cars?',
         'correct_answer': 'Liability in a crash and how the vehicle should decide between harms',
         'distractors': ['Data governance and patient privacy',
                         'Manufacturing costs and vehicle performance',
                         'Driver training and road safety regulations']},
        MULTI_TOPIC,
    )
    assert report.rivals == []
    assert report.ok is True


def test_a_name_mentioned_elsewhere_is_not_a_rival():
    # "Australia" có trong tài liệu nhưng không phải nơi chi 14 tỷ.
    report = score_question(
        {'question_text': 'Which region plans to contribute at least 14 billion to AI investment?',
         'correct_answer': 'The European Union',
         'distractors': ['Australia', 'The United States', 'China']},
        MULTI_TOPIC,
    )
    assert report.rivals == []
    assert report.ok is True


# ---- hai chỗ phép chấm tự bắt oan, phát hiện khi soi câu gemini-3.8-flash sinh -------

def test_a_word_containing_not_is_not_a_negative_question():
    # "footnote" có chuỗi "not" bên trong; đây là câu hỏi thường.
    assert is_negative_question(
        'Based on the footnote, how much has China contributed?') is False


def test_a_real_negation_is_still_caught():
    assert is_negative_question('Which of these is NOT mentioned in the excerpt?') is True
    assert is_negative_question('Điều nào sau đây KHÔNG được nêu trong tài liệu?') is True
    assert is_negative_question('All of these are listed except one. Which?') is True


def test_options_differing_only_by_a_number_are_not_echoes():
    # Bộ nhiễu bằng số là hợp lệ: chỉ khác con số thì không phải nhại lại.
    report = score_question(
        {'question_text': 'How much did China plan to contribute at the low end?',
         'correct_answer': 'At least 8 billion',
         'distractors': ['At least 4 billion', 'At least 2 billion', 'At least 20 billion']},
        'Low-end estimates put China at least 8 billion in AI investment.',
    )
    assert report.echoes == []
    assert 'distractor_echoes_answer' not in report.flags


NUMERIC_EXCERPT = (
    'Low-end estimates put China at least 8 billion in planned AI investment, '
    'while the European Union plans at least 14 billion euros.'
)


def test_a_wrong_number_is_not_what_the_document_says():
    assert support('at least 8 billion', NUMERIC_EXCERPT) > 0.8
    assert support('at least 4 billion', NUMERIC_EXCERPT) < 0.45


def test_a_numeric_distractor_set_passes():
    report = score_question(
        {'question_text': 'How much did China plan to contribute at the low end?',
         'correct_answer': 'At least 8 billion',
         'distractors': ['At least 4 billion', 'At least 2 billion', 'At least 20 billion']},
        NUMERIC_EXCERPT,
    )
    assert report.rivals == []
    assert report.ok is True


# ---- rank_by_quality: clean questions first, nothing thrown away ----------------------

def _item(question, answer, distractors, excerpt=EXCERPT):
    return {'question_text': question, 'correct_answer': answer,
            'distractors': distractors, '_excerpt': excerpt}


CLEAN = _item('What undermines the safety benefit of mobile phones?',
              'theft, loss and depleted batteries',
              ['a lack of storage space', 'slow internet', 'small screens'])
RIVAL = _item('What role do mobile phones play in personal safety?',
              'a source of risk', ['a lifeline', 'a way to pay rent', 'a school requirement'])


def test_a_clean_question_goes_before_a_flawed_one():
    from ml_pipeline.question_quality import rank_by_quality
    assert rank_by_quality([RIVAL, CLEAN]) == [CLEAN, RIVAL]


def test_equally_good_questions_keep_their_order():
    from ml_pipeline.question_quality import rank_by_quality
    other = _item('What do phones let young people do in emergencies?', 'summon help',
                  ['buying snacks', 'playing games', 'watching films'])
    assert rank_by_quality([CLEAN, other]) == [CLEAN, other]
    assert rank_by_quality([other, CLEAN]) == [other, CLEAN]


def test_nothing_is_dropped_only_reordered():
    # When every question is flawed the quiz still needs its count; the least
    # flawed are used first rather than handing back an empty quiz.
    from ml_pipeline.question_quality import rank_by_quality
    items = [RIVAL, CLEAN, RIVAL]
    assert len(rank_by_quality(items)) == 3


def test_fewer_flags_go_before_more():
    from ml_pipeline.question_quality import rank_by_quality
    two_flags = _item('Phones?', 'a source of risk', ['a lifeline'])   # rival + too few + short
    assert rank_by_quality([two_flags, RIVAL]) == [RIVAL, two_flags]


def test_a_question_without_its_passage_is_not_trusted_over_one_with():
    from ml_pipeline.question_quality import rank_by_quality
    lost = {**CLEAN, '_excerpt': ''}
    assert rank_by_quality([lost, CLEAN])[0] is CLEAN


# ---- words a distractor shares with the answer prove nothing --------------------------
# Found on a real Gemini quiz: "The accuracy principle" was called "also true" next
# to the answer "The integrity and confidentiality principle", only because both say
# "the ... principle". What makes a distractor a rival is what sets it apart.

BREACH = ("The shadow spreadsheet looked like diligence. In fact it is a live breach "
          "of the integrity and confidentiality principle under data protection law.")


def test_shared_template_words_do_not_make_a_distractor_true():
    report = score_question(
        {'question_text': 'Which principle does the shadow spreadsheet breach?',
         'correct_answer': 'The integrity and confidentiality principle',
         'distractors': ['The accuracy principle', 'The purpose limitation principle',
                         'The storage limitation principle']},
        BREACH,
    )
    assert report.rivals == []
    assert report.ok is True


def test_a_distractor_whose_own_words_are_in_the_answer_sentence_is_still_a_rival():
    report = score_question(
        {'question_text': 'Which principle does the shadow spreadsheet breach?',
         'correct_answer': 'The integrity principle',
         'distractors': ['The confidentiality principle', 'The accuracy principle',
                         'The storage limitation principle']},
        BREACH,
    )
    # "confidentiality" is breached too, by the same sentence: two right answers.
    assert report.rivals == ['The confidentiality principle']
