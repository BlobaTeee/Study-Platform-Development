"""The local translator: how a paragraph is cut into sentences, and that
importing it costs nothing until a text is translated."""
import subprocess
import sys

from ml_pipeline.translator import split_sentences


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
