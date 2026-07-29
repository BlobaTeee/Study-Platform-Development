"""Regression test for the reduce-without-initializer bug in _source_filter.

_source_filter used to build its OR with `functools.reduce(fn, iterable)` and
no initializer. Without an initializer, reduce() seeds the accumulator with
the raw first item of the iterable rather than an empty value, so with one
source id the "accumulator" was never a Q at all — it was the plain int
`source_ids[0]` — and with two or more, the first `acc | Q(...)` blew up with
`TypeError: unsupported operand type(s) for |: 'int' and 'Q'`. Since
_question_pool and _source_accuracy both call this whenever a notebook has
any sources, mock test creation 500'd for the ordinary case (any notebook with
sources) and only "worked" for the degenerate empty-sources case, which never
reaches this function.

Building a Q needs Django's app registry (django.setup()) but not a live
database connection, so this exercises the real `quizzes.views._source_filter`
without a test database.
"""
import os
import sys
from pathlib import Path

import django
from django.db.models import Q

_BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "studyplatform.settings")
django.setup()

from quizzes.views import _source_filter  # noqa: E402  (needs django.setup() first)


def test_a_single_source_id_returns_a_q_not_an_int():
    # The exact regression: reduce() with no initializer and a one-item
    # iterable returns that raw item unchanged, so the broken code handed
    # back the int 5 here instead of a Q.
    result = _source_filter('', [5])
    assert isinstance(result, Q)


def test_two_source_ids_produce_a_q_mentioning_both():
    result = _source_filter('', [5, 7])
    assert isinstance(result, Q)
    values = {value for _, value in result.children}
    assert 'source:5' in values
    assert 'source:7' in values


def test_two_source_ids_are_ored_not_anded():
    result = _source_filter('', [5, 7])
    assert result.connector == Q.OR


def test_no_source_ids_matches_nothing_rather_than_everything():
    # A bare Q() matches every row, which would silently turn the "narrow to
    # this notebook's sources" prefilter into a full scan of the user's whole
    # quiz history. It must match nothing instead.
    result = _source_filter('', [])
    assert isinstance(result, Q)
    assert result.children == [('pk__in', [])]
