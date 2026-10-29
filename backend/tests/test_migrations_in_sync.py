"""The models and the migrations agree.

A model change without its migration, or a key-type default that drifts,
shows up here instead of as a surprise `migrate` against the shared dev
database (see the 2026-10-28 note on 64-bit keys in quizzes/apps.py).
"""
from io import StringIO

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_no_migration_is_waiting_to_be_written():
    out = StringIO()
    try:
        call_command('makemigrations', '--check', '--dry-run', stdout=out, stderr=out)
    except SystemExit:
        pytest.fail('makemigrations would write:\n' + out.getvalue())
