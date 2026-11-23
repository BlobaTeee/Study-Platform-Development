"""Two lanes: writing goes to the strong model first, short judgements the
student is waiting on go to the fast model first, each covering for the other.

Measured on one grading prompt (2026-11-15): 3.8-flash, flash-latest and
2.5-flash all timed out at about 28 s; 3.1-flash-lite with thinking 'low'
answered in 6.2 s and graded it right.
"""
import pytest

from notebooks.services import gemini_client
from notebooks.services.gemini_client import generate_json
from notebooks.services.model_lane import is_quick, quick


class _Models:
    def __init__(self, script=None):
        self.script = script or {}
        self.calls = []

    def generate_content(self, model, contents, config=None, **kwargs):
        self.calls.append((model, config))
        outcome = self.script.get(model, '{"ok": true}')
        if isinstance(outcome, Exception):
            raise outcome
        return type('R', (), {'text': outcome})()


@pytest.fixture
def fake(monkeypatch, settings):
    settings.GEMINI_MODEL = 'main'
    settings.GEMINI_MODEL_FALLBACKS = 'fast'
    settings.GEMINI_FAST_MODEL = 'fast'
    settings.GEMINI_THINKING = 'default'
    settings.GEMINI_FAST_THINKING = 'low'
    settings.GEMINI_TIMEOUT_SECONDS = 30
    settings.GEMINI_FAST_TIMEOUT_SECONDS = 12
    gemini_client.forget_failures()

    def install(**kwargs):
        models = _Models(**kwargs)
        monkeypatch.setattr(gemini_client, '_get_client', lambda: type('C', (), {'models': models})())
        return models
    yield install
    gemini_client.forget_failures()


def test_writing_asks_the_main_model_first_and_the_fast_one_after(fake):
    models = fake(script={'main': Exception('503 UNAVAILABLE. overloaded')})
    assert generate_json('x') == {'ok': True}
    assert [m for m, _ in models.calls] == ['main', 'fast']
    assert models.calls[0][1].thinking_config is None          # left to the model


def test_the_quick_lane_asks_the_fast_model_first_with_low_thinking(fake):
    models = fake()
    with quick():
        generate_json('x')
    model, config = models.calls[0]
    assert model == 'fast' and config.thinking_config.thinking_level.lower() == 'low'


def test_the_quick_lane_falls_back_to_the_main_model(fake):
    models = fake(script={'fast': Exception('503 UNAVAILABLE. overloaded')})
    with quick():
        assert generate_json('x') == {'ok': True}
    assert [m for m, _ in models.calls] == ['fast', 'main']


def test_the_quick_lane_waits_less(fake, monkeypatch):
    fake()
    waits = []
    monkeypatch.setattr(gemini_client, '_call_with_deadline', lambda call, seconds: (waits.append(seconds), call())[1])
    generate_json('x')
    with quick():
        generate_json('x')
    assert waits == [30.0, 12.0]


def test_the_lane_ends_with_its_block():
    assert is_quick() is False
    with quick():
        assert is_quick() is True
    assert is_quick() is False


@pytest.mark.django_db
def test_short_judgements_run_on_the_quick_lane(monkeypatch, user, notebook):
    # Grading a practice answer, a hint and the typed-answer tie-break are
    # judgements the student waits on; writing problems is not.
    from exercises.models import Exercise
    from exercises.services import grading, problems
    seen = []

    class Provider:
        name = 'fake'

        def generate_json(self, prompt):
            seen.append(is_quick())
            return {'met': [1], 'first_wrong_step': None, 'hint': 'Why?', 'problems': []}

    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: Provider())
    ex = Exercise.objects.create(user=user, notebook=notebook, prompt='Company A delivered 20 days late. What can B do?',
                                 reference={'solution': ['a'], 'checkpoints': [{'id': 1, 'text': 'x', 'basis': ''}],
                                            'mistakes': []})
    grading.grade(ex, ['A is in breach.'])
    grading.hint(ex, ['A is in breach.'])
    with pytest.raises(Exception):
        problems.own_rubric('Solve 2x + 3 = 11 for x and check it.')     # writing: not quick
    assert seen == [True, True, False]


def test_a_long_read_gets_the_read_timeout_and_resets(settings):
    from notebooks.services import gemini_client
    from notebooks.services.model_lane import is_long, long_read
    settings.GEMINI_TIMEOUT_SECONDS, settings.GEMINI_READ_TIMEOUT_SECONDS = 30, 90
    with long_read():
        assert is_long()
        assert gemini_client._wait_seconds() == 90
    assert not is_long()
    assert gemini_client._wait_seconds() == 30


def test_reading_a_photo_runs_in_the_long_lane(client, monkeypatch):
    from notebooks.services.model_lane import is_long
    seen = {}

    class Reader:
        def generate_json_from_images(self, prompt, images):
            seen['long'] = is_long()
            return {'found': True, 'questions': [{'label': 'Câu 1', 'text': 'Tính $2+2$.'}]}

    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: Reader())
    from django.core.files.uploadedfile import SimpleUploadedFile
    res = client.post('/api/exercises/read-photo/', {'image': SimpleUploadedFile('a.jpg', b'\xff\xd8\xff\xe0' + b'0' * 99)},
                      format='multipart')
    assert res.status_code == 200 and seen['long'] is True
