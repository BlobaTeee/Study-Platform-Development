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
