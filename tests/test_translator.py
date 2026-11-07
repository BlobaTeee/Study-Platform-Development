"""The local translator: how a paragraph is cut into sentences, how a text
is prepared for the model and put back, and that importing it costs nothing
until a text is translated."""
import subprocess
import sys

from ml_pipeline.translator import (answer_from, answer_prompt, as_sentence_case, first_letter_as_in, shield,
                                    split_sentences, unshield)


def test_a_paragraph_is_cut_into_its_sentences():
    text = 'Air is a poor conductor. It insulates well! Why? Because 2 layers trap it.'
    assert split_sentences(text) == ['Air is a poor conductor.', 'It insulates well!', 'Why?', 'Because 2 layers trap it.']


def test_a_label_is_one_sentence():
    assert split_sentences('  Phase Change Energy ') == ['Phase Change Energy']


def test_abbreviations_and_decimals_do_not_cut():
    assert split_sentences('The value is 3.5 e.g. for water.') == ['The value is 3.5 e.g. for water.']


def test_vietnamese_capitals_start_a_sentence():
    assert split_sentences('Nước sôi ở 100 độ. Đá tan ở 0 độ.') == ['Nước sôi ở 100 độ.', 'Đá tan ở 0 độ.']


def test_importing_does_not_load_torch():
    code = 'import sys, ml_pipeline.translator; print("torch" in sys.modules)'
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == 'False'


# Names written in Title Case read to the model like menu items ("Virus Structure" → "Cấu trúc Vi rútName",
# "Nutrient Cycles" → "Công thức tính toán"); in sentence case it translates them (notebook 12).
def test_a_title_case_name_is_put_in_sentence_case():
    assert as_sentence_case('Nutrient Cycles') == 'Nutrient cycles'
    assert as_sentence_case("Air's Insulating Properties") == "Air's insulating properties"


def test_acronyms_and_mixed_case_words_stay_as_written():
    assert as_sentence_case('EM Wave Energy and Frequency') == 'EM wave energy and frequency'
    assert as_sentence_case('Brønsted-Lowry Acids and Bases') == 'Brønsted-Lowry acids and bases'
    assert as_sentence_case('Vitamin A Sources') == 'Vitamin A sources'


def test_sentences_and_names_already_in_sentence_case_are_left_alone():
    assert as_sentence_case('Cell division for growth') == 'Cell division for growth'
    assert as_sentence_case('The Sun Gives Energy To Plants.') == 'The Sun Gives Energy To Plants.'
    assert as_sentence_case('Macromolecules') == 'Macromolecules'


def test_the_translation_starts_with_a_capital_when_the_text_did():
    assert first_letter_as_in('Nguyên phân tạo ra hai tế bào con.', 'mitosis produces two daughter cells.') \
        == 'Mitosis produces two daughter cells.'
    assert first_letter_as_in('mRNA carries the code.', 'mRNA mang mã.') == 'mRNA mang mã.'
    assert first_letter_as_in('(Air) insulates.', '(không khí) cách nhiệt.') == '(Không khí) cách nhiệt.'


# The model's vocabulary has no λ Δ ≤ → ° ø … and silently drops them; it reads
# super- and subscripts as plain digits ("m²" → "m2"). They travel as <n>.
KNOWN = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,;:()+-=/<>\'"')


def test_characters_the_model_cannot_read_travel_as_placeholders():
    text, spans = shield('pH ≤ 7 and λ = v/f', KNOWN.__contains__)
    assert (text, spans) == ('pH <0> 7 and <1> = v/f', ['≤', 'λ'])


def test_a_run_of_such_characters_is_one_placeholder():
    assert shield('C₆H₁₂O₆', KNOWN.__contains__) == ('C<0>H<1>O<2>', ['₆', '₁₂', '₆'])
    assert shield('100 °C', KNOWN.__contains__) == ('100 <0>C', ['°'])


def test_a_name_with_such_a_letter_travels_whole():
    # Only the ø as a placeholder, the model garbled the rest: "Br<0>axit lương" (notebook 12).
    assert shield('Brønsted-Lowry acids', KNOWN.__contains__) == ('<0> acids', ['Brønsted-Lowry'])
    assert shield('so Δv = 0', KNOWN.__contains__) == ('so <0> = 0', ['Δv'])


def test_superscripts_are_kept_even_when_the_model_knows_them():
    assert shield('area in m²', lambda c: True) == ('area in m<0>', ['²'])


def test_a_text_without_such_characters_is_unchanged():
    assert shield('Air insulates well.', KNOWN.__contains__) == ('Air insulates well.', [])


def test_placeholders_are_put_back():
    assert unshield('pH <0> 7 và <1> = v/f', ['≤', 'λ']) == 'pH ≤ 7 và λ = v/f'


def test_a_lost_or_repeated_placeholder_gives_nothing():
    assert unshield('pH 7 và <1> = v/f', ['≤', 'λ']) is None
    assert unshield('<0> pH <0> 7', ['≤']) is None


def test_a_blank_to_fill_travels_as_a_placeholder():
    # The model drops "___" from a fill-in-the-blank sentence; as <0> it keeps its place.
    assert shield('or ___, a system contains.', KNOWN.__contains__) == ('or <0>, a system contains.', ['___'])


# A short answer alone is a word without a sense ("Force" → "Buộc", "nguyên phân" →
# "integral"); asked as the answer to its question, the model picks the sense the question means.
def test_a_short_answer_is_asked_with_its_question():
    assert answer_prompt('Force', 'What changes angular velocity?', 'en') == 'What changes angular velocity? Answer: Force.'
    assert answer_prompt('nguyên phân', 'Nhân phân chia gọi là gì?', 'vi') == 'Nhân phân chia gọi là gì? Đáp án: nguyên phân.'


def test_the_answer_is_read_after_the_last_answer_word():
    assert answer_from('Cần gì để thay đổi vận tốc góc? Đáp án: Lực.', 'vi') == 'Lực'
    assert answer_from('Đại lượng nào đo bằng kilôgam? Câu trả lời là khối lượng.', 'vi') == 'khối lượng'
    assert answer_from('Tính chất nào? Trả lời: Điện tích.', 'vi') == 'Điện tích'
    assert answer_from('What is measured in kilograms? Answer: mass.', 'en') == 'mass'


def test_no_answer_word_means_no_answer():
    assert answer_from('Quá trình nhân phân chia được gọi là epistasis.', 'vi') is None
    assert answer_from('Đáp án:', 'vi') is None
