"""Which language a source is written in — enough to tell the generator
what to write in, and to keep the English-only extractive path off
Vietnamese text."""
import importlib.util
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1] / "ml_pipeline" / "language.py")


def _load():
    spec = importlib.util.spec_from_file_location("language_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lang = _load()

VI = ("Quang hợp là quá trình thực vật hấp thụ khí carbon dioxide và nước, "
      "sử dụng năng lượng ánh sáng để tạo ra glucose và giải phóng oxy.")
EN = ("Photosynthesis is the process by which plants absorb carbon dioxide and "
      "water and use light energy to make glucose, releasing oxygen.")


def test_vietnamese_prose_is_vietnamese():
    assert lang.detect_language(VI) == "vi"


def test_english_prose_is_english():
    assert lang.detect_language(EN) == "en"


def test_vietnamese_without_many_diacritics_still_reads_as_vietnamese_by_its_words():
    # Chat-style Vietnamese often drops tone marks; the function words remain.
    assert lang.detect_language("cac ban can hoc bai nay va lam bai tap cua minh khong") == "vi"


def test_english_with_a_vietnamese_name_is_still_english():
    assert lang.detect_language("Nguyễn Văn A presented the results of the experiment to the class.") == "en"


def test_mixed_document_goes_with_the_majority():
    assert lang.detect_language(VI * 3 + " " + EN) == "vi"
    assert lang.detect_language(EN * 3 + " " + VI) == "en"


def test_other_scripts_are_other():
    assert lang.detect_language("光合作用是植物吸收二氧化碳和水的过程。") == "other"


def test_empty_is_other():
    assert lang.detect_language("") == "other"


def test_language_name_for_prompts():
    assert lang.language_name("vi") == "Vietnamese"
    assert lang.language_name("en") == "English"
    assert lang.language_name("other") == "the same language as the excerpt"
