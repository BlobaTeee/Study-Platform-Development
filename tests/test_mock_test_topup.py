"""How much a mock test generates when its notebook cannot fill the paper."""
import importlib.util
from pathlib import Path

_MODULE_PATH = (Path(__file__).resolve().parents[1]
                / "backend" / "quizzes" / "services" / "topup.py")


def _load():
    spec = importlib.util.spec_from_file_location("topup_under_test", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load()
questions_to_request = _mod.questions_to_request
should_continue = _mod.should_continue
QUIZ_MAX_PER_GENERATION = _mod.QUIZ_MAX_PER_GENERATION
MAX_TOPUP_ROUNDS = _mod.MAX_TOPUP_ROUNDS
TOPUP_TIME_BUDGET_SECONDS = _mod.TOPUP_TIME_BUDGET_SECONDS


# --- how many to ask for ---

def test_asks_for_exactly_the_shortfall():
    assert questions_to_request(pool_size=8, requested=20) == 12


def test_a_covered_pool_asks_for_nothing():
    assert questions_to_request(pool_size=20, requested=20) == 0


def test_an_oversized_pool_asks_for_nothing():
    # Not a negative number, which the generator's own clamp would turn back
    # into its four-question floor.
    assert questions_to_request(pool_size=50, requested=20) == 0


def test_a_large_shortfall_is_capped_at_one_generation():
    # 50 questions against an empty notebook must not be asked for at once:
    # generate_quiz_for_sources clamps to 15 and silently returns fewer than
    # asked, so an uncapped caller would wait for questions never coming.
    assert questions_to_request(pool_size=0, requested=50) == QUIZ_MAX_PER_GENERATION


# --- whether to run another round ---

def _kwargs(**over):
    base = dict(pool_size=5, previous_pool_size=0, requested=20,
                rounds_done=1, seconds_spent=1.0)
    base.update(over)
    return base


def test_continues_while_short_and_making_progress():
    assert should_continue(**_kwargs()) is True


def test_stops_once_the_paper_is_coverable():
    assert should_continue(**_kwargs(pool_size=20)) is False


def test_stops_at_the_round_cap():
    assert should_continue(**_kwargs(rounds_done=MAX_TOPUP_ROUNDS)) is False


def test_stops_once_the_time_budget_is_spent():
    assert should_continue(**_kwargs(seconds_spent=TOPUP_TIME_BUDGET_SECONDS)) is False


def test_stops_when_a_round_added_nothing():
    # A document that has given up every question it can produce returns
    # duplicates the pool rejects. Without this the whole budget is spent on
    # rounds that cannot change the outcome.
    assert should_continue(**_kwargs(pool_size=5, previous_pool_size=5)) is False


def test_stops_when_a_round_somehow_shrank_the_pool():
    assert should_continue(**_kwargs(pool_size=4, previous_pool_size=5)) is False


def test_the_first_round_always_runs():
    # rounds_done=0 means nothing has been generated yet, so there is no
    # previous size to compare against; the no-progress test must not fire and
    # block generation before it has been tried even once.
    assert should_continue(pool_size=0, previous_pool_size=0, requested=20,
                           rounds_done=0, seconds_spent=0.0) is True


def test_an_empty_notebook_still_starts_a_round():
    assert questions_to_request(pool_size=0, requested=20) == QUIZ_MAX_PER_GENERATION
