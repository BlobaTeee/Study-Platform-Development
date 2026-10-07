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
