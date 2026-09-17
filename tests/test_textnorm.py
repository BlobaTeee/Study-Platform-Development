"""Extracted text is normalised once, at ingest, so everything downstream
(search, exact-match grading, TF-IDF) sees plain letters."""
import importlib.util
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "notebooks" / "services" / "textnorm.py")


def _load():
    spec = importlib.util.spec_from_file_location("textnorm_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tn = _load()


def test_ligatures_become_letters():
    # PDFs typeset "fi", "fl", "ffi" as single glyphs; pypdf hands them over as-is.
    assert tn.normalise_text("ﬁnancial ﬂow ofﬁce") == "financial flow office"


def test_fullwidth_and_nbsp_are_folded():
    assert tn.normalise_text("Ｄａｔａ science") == "Data science"


def test_plain_text_is_untouched():
    assert tn.normalise_text("Plants absorb carbon dioxide.\n\nNext paragraph.") == \
        "Plants absorb carbon dioxide.\n\nNext paragraph."


def test_none_and_empty_are_safe():
    assert tn.normalise_text(None) == ""
    assert tn.normalise_text("") == ""
