"""Khi một model Gemini trục trặc, cái tiếp theo phải được dùng."""
import pytest

from notebooks.services import gemini_client
from notebooks.services.gemini_client import (
    GeminiGenerationError, GeminiQuotaError, generate_json,
)


class _Models:
    def __init__(self, script):
        self.script = script          # {model: Exception | text}
        self.calls = []

    def generate_content(self, model, contents, config=None, **kwargs):
        self.calls.append(model)
        outcome = self.script.get(model, '{"ok": true}')
        if isinstance(outcome, Exception):
            raise outcome
        return type('R', (), {'text': outcome})()


@pytest.fixture
def fake(monkeypatch, settings):
    settings.GEMINI_MODEL = 'first'
    settings.GEMINI_MODEL_FALLBACKS = 'second,third'

    def install(script):
        models = _Models(script)
        monkeypatch.setattr(gemini_client, '_get_client',
                            lambda: type('C', (), {'models': models})())
        return models
    return install


def test_an_overloaded_model_hands_over_to_the_next_one(fake):
    models = fake({'first': Exception('503 UNAVAILABLE. The model is overloaded.'),
                   'second': '{"questions": ["ok"]}'})

    assert generate_json('x') == {'questions': ['ok']}
    assert models.calls == ['first', 'second']


def test_a_server_error_also_hands_over(fake):
    models = fake({'first': Exception('500 INTERNAL'), 'second': '{"ok": true}'})
    assert generate_json('x') == {'ok': True}
    assert models.calls == ['first', 'second']


def test_a_retired_model_is_skipped_rather_than_fatal(fake):
    # Google retires model ids; the fallback list exists for exactly this.
    models = fake({'first': Exception('404 NOT_FOUND. This model is no longer available to new users.'),
                   'second': '{"ok": true}'})
    assert generate_json('x') == {'ok': True}
    assert models.calls == ['first', 'second']


def test_quota_still_reads_as_quota_after_every_model_is_tried(fake):
    models = fake({m: Exception('429 RESOURCE_EXHAUSTED') for m in ('first', 'second', 'third')})
    with pytest.raises(GeminiQuotaError):
        generate_json('x')
    assert models.calls == ['first', 'second', 'third']


def test_transient_failures_everywhere_end_as_a_generation_error(fake):
    fake({m: Exception('503 UNAVAILABLE') for m in ('first', 'second', 'third')})
    with pytest.raises(GeminiGenerationError) as exc:
        generate_json('x')
    assert not isinstance(exc.value, GeminiQuotaError)


def test_a_bad_request_fails_at_once_without_burning_the_other_models(fake):
    models = fake({'first': Exception('400 INVALID_ARGUMENT: prompt too long')})
    with pytest.raises(GeminiGenerationError):
        generate_json('x')
    assert models.calls == ['first']


def test_a_request_the_server_cancelled_hands_over(fake):
    # Google answers 499 CANCELLED when it drops a request on its side; the
    # next model usually answers.
    models = fake({'first': Exception("499 CANCELLED. {'error': {'code': 499, 'status': 'CANCELLED'}}"),
                   'second': '{"ok": true}'})

    assert generate_json('x') == {'ok': True}
    assert models.calls == ['first', 'second']


def test_an_image_is_sent_before_the_prompt(fake, monkeypatch):
    seen = []

    class _Seeing(_Models):
        def generate_content(self, model, contents, config=None, **kwargs):
            seen.append(contents)
            return type('R', (), {'text': '{"found": true}'})()

    models = _Seeing({})
    monkeypatch.setattr(gemini_client, '_get_client', lambda: type('C', (), {'models': models})())

    assert generate_json('read this', images=[(b'\xff\xd8\xff', 'image/jpeg')]) == {'found': True}
    parts = seen[0]
    assert isinstance(parts, list) and parts[-1] == 'read this'
    assert getattr(parts[0], 'inline_data', None) is not None
    assert parts[0].inline_data.mime_type == 'image/jpeg'


def test_a_text_prompt_is_still_sent_as_plain_text(fake, monkeypatch):
    seen = []

    class _Seeing(_Models):
        def generate_content(self, model, contents, config=None, **kwargs):
            seen.append(contents)
            return type('R', (), {'text': '{"ok": true}'})()

    models = _Seeing({})
    monkeypatch.setattr(gemini_client, '_get_client', lambda: type('C', (), {'models': models})())
    generate_json('just text')
    assert seen == ['just text']


def test_the_chain_stops_when_its_time_is_spent(fake, monkeypatch, settings):
    """With Gemini overloaded, one request went through every model for over
    five minutes; the chain now shares one budget and says so when it is spent."""
    settings.GEMINI_TOTAL_SECONDS = 45
    settings.GEMINI_TIMEOUT_SECONDS = 30
    now = [1000.0]
    monkeypatch.setattr(gemini_client.time, 'monotonic', lambda: now[0])
    waits = []

    def stalls(call, seconds):
        waits.append(seconds)
        now[0] += seconds                       # the model sat for its whole deadline
        raise GeminiGenerationError(f'Model timed out after {seconds:g}s')
    monkeypatch.setattr(gemini_client, '_call_with_deadline', stalls)
    fake({})

    with pytest.raises(GeminiGenerationError):
        generate_json('x')
    assert waits == [30, 15]                    # the second model gets what is left; no third


def test_a_retry_shares_the_budget_of_the_first_try(monkeypatch, settings):
    from notebooks.services import model_lane
    now = [0.0]
    monkeypatch.setattr(model_lane.time, 'monotonic', lambda: now[0])
    with model_lane.within(90):
        now[0] = 60
        with model_lane.within(90):              # an inner budget never outlasts the outer one
            assert model_lane.seconds_left() == 30
    assert model_lane.seconds_left() is None
