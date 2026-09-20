"""Which questions a student still owes: answered wrong, not yet answered
right twice in a row since."""
import importlib.util
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "quizzes" / "services" / "mistakes.py")


def _load():
    spec = importlib.util.spec_from_file_location("mistakes_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mk = _load()


def test_a_question_never_missed_is_not_owed():
    assert mk.is_owed([True, True, True]) is False
    assert mk.is_owed([]) is False


def test_one_wrong_answer_puts_it_in_the_bank():
    assert mk.is_owed([False]) is True
    assert mk.is_owed([True, False]) is True


def test_two_correct_in_a_row_after_a_miss_clears_it():
    assert mk.is_owed([False, True, True]) is False


def test_one_correct_after_a_miss_is_not_enough():
    assert mk.is_owed([False, True]) is True


def test_a_miss_after_clearing_reopens_it():
    assert mk.is_owed([False, True, True, False]) is True


def test_unanswered_attempts_do_not_count_either_way():
    # None = left blank; it is neither a miss nor a success.
    assert mk.is_owed([False, None, True, True]) is False
    assert mk.is_owed([None, None]) is False


def test_owed_questions_from_a_mixed_timeline():
    # (question_id, answered_at, is_correct), any order; per question the
    # timeline is sorted by time before the rule runs.
    events = [
        (1, 3, True), (1, 1, False), (1, 2, True),          # miss, right, right -> cleared
        (2, 1, False), (2, 2, True),                        # miss, right -> still owed
        (3, 1, True),                                       # never missed
        (4, 2, False), (4, 1, True),                        # right then miss -> owed
    ]
    assert mk.owed_question_ids(events) == {2, 4}
