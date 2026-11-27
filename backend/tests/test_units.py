"""Units after a number are written as their symbols."""
import random

import pytest

from notebooks.services.quiz_shaping import shape_quiz_question
from notebooks.services.units import unit_symbols, unit_symbols_in_math
from notebooks.services.writing_style import tidy_prose


@pytest.mark.parametrize('text, expected', [
    ('Công 500 joule, áp suất 2 Pascal', 'Công 500 J, áp suất 2 Pa'),
    ('lực 10 newton', 'lực 10 N'),
    ('300 jun', '300 J'),
    ('v = 3 mét trên giây', 'v = 3 m/s'),
    ('72 kilômét trên giờ', '72 km/h'),
    ('9,8 meters per second squared', '9,8 m/s²'),
    ('5 ki-lô-gam, 3 mét vuông, 2 cubic meters, 1,5 lít', '5 kg, 3 m², 2 m³, 1,5 L'),
    ('25 độ C, 100 degrees Celsius', '25 °C, 100 °C'),
    ('10 kilopascals, 3 kilowatt-hours', '10 kPa, 3 kWh'),
    ('điện trở 10 ôm, 220 vôn, 2 ampe', 'điện trở 10 Ω, 220 V, 2 A'),
    ('50 héc', '50 Hz'),
])
def test_spelled_units_become_symbols(text, expected):
    assert unit_symbols(text) == expected


@pytest.mark.parametrize('text', [
    'định luật 2 Newton',          # Newton's second law, not 2 N
    'ngày 5 Jun 2024',             # a month
    'dùng 2 ampe kế',              # two ammeters
    'học 2 giờ mỗi ngày',          # time alone is not a measurement
    'rộng 50 héc-ta',              # hectares
    'the joule is the unit of energy',
    'đơn vị của áp suất là pascal',
    '12 V and 3 m/s',
])
def test_left_alone(text):
    assert unit_symbols(text) == text


def test_units_inside_latex():
    assert unit_symbols_in_math(r'W = 500\,\text{joule}') == r'W = 500\,\mathrm{J}'
    assert unit_symbols_in_math(r'R = 10\text{ ohm}') == r'R = 10\,\mathrm{\Omega}'
    assert unit_symbols_in_math(r'V = \text{dài}') == r'V = \text{dài}'


def test_tidy_prose_writes_symbols_in_text_and_maths():
    out = tidy_prose(r'Vật nhận công 500 joule và $p = 2\,\text{pascal}$, sau đó $5$ newton.')
    assert '500 J' in out and r'\mathrm{Pa}' in out and '$5$ N' in out


def test_quiz_options_and_answer_change_together():
    shaped = shape_quiz_question({'question_text': 'Công là bao nhiêu?', 'correct_answer': '500 joule',
                                  'distractors': ['250 joule', '50 joule']}, random.Random(1))
    assert shaped['correct_answer'] == '500 J'
    assert shaped['correct_answer'] in shaped['options']
    assert set(shaped['options']) == {'500 J', '250 J', '50 J'}


def test_short_answer_matches_either_spelling():
    from exercises.services.grading import short_matches
    assert short_matches('500 joule', ['500 J'])
    assert short_matches('500 J', ['500 jun'])
