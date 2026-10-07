"""Model vừa chết thì lần sau đừng chờ nó nữa.

Mỗi model không trả lời tốn trọn một deadline trước khi nhường cho model sau,
nên khi model đầu chuỗi đang quá tải thì *mọi* lượt sinh đều phải trả cái giá
đó. Ghi nhớ trong ít phút là người dùng thứ hai không phải chờ lại.
"""
import pytest

from notebooks.services import gemini_client
from notebooks.services.gemini_client import generate_json


class _Models:
    def __init__(self, script):
        self.script = script
        self.calls = []

    def generate_content(self, model, contents, config=None, **kwargs):
        self.calls.append(model)
        outcome = self.script.get(model, '{"questions": ["ok"]}')
        if isinstance(outcome, Exception):
            raise outcome
        return type('R', (), {'text': outcome})()


@pytest.fixture
def fake(monkeypatch, settings):
    settings.GEMINI_MODEL = 'first'
    settings.GEMINI_MODEL_FALLBACKS = 'second'
    settings.GEMINI_COOLDOWN_SECONDS = 300
    gemini_client.forget_failures()

    def install(script):
        models = _Models(script)
        monkeypatch.setattr(gemini_client, '_get_client',
                            lambda: type('C', (), {'models': models})())
        return models
    return install


def test_a_model_that_just_timed_out_is_skipped_next_time(fake):
    models = fake({'first': Exception('ReadTimeout: timed out')})

    generate_json('x')
    generate_json('x')

    # Lần đầu phải thử 'first' rồi nhường; lần sau đi thẳng tới 'second'.
    assert models.calls == ['first', 'second', 'second']


def test_the_cooldown_expires(fake, monkeypatch):
    models = fake({'first': Exception('503 UNAVAILABLE')})
    now = [1000.0]
    monkeypatch.setattr(gemini_client.time, 'monotonic', lambda: now[0])

    generate_json('x')
    now[0] += 301
    generate_json('x')

    assert models.calls == ['first', 'second', 'first', 'second']


def test_a_working_model_is_never_skipped(fake):
    models = fake({})

    generate_json('x')
    generate_json('x')

    assert models.calls == ['first', 'first']


def test_a_recovered_model_is_trusted_again(fake, monkeypatch):
    models = fake({'first': Exception('503 UNAVAILABLE')})
    now = [1000.0]
    monkeypatch.setattr(gemini_client.time, 'monotonic', lambda: now[0])

    generate_json('x')
    models.script.clear()          # 'first' hồi phục
    now[0] += 301
    generate_json('x')
    generate_json('x')

    assert models.calls[-2:] == ['first', 'first']


def test_every_model_in_cooldown_still_gets_one_last_try(fake):
    # Thà chờ còn hơn báo lỗi khi chưa thử gì: nếu bỏ qua hết thì lượt sinh
    # thất bại dù có thể model đã hồi.
    models = fake({'first': Exception('503 UNAVAILABLE'),
                   'second': Exception('503 UNAVAILABLE')})

    with pytest.raises(Exception):
        generate_json('x')
    models.calls.clear()
    models.script.clear()

    assert generate_json('x') == {'questions': ['ok']}
    assert models.calls == ['first']


# ---- hết lượt trong ngày ---------------------------------------------------------

DAILY = Exception("429 RESOURCE_EXHAUSTED. quotaId: 'GenerateRequestsPerDayPerProjectPerModel-FreeTier'")
PER_MINUTE = Exception("429 RESOURCE_EXHAUSTED. quotaId: 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier'")


def test_a_model_out_of_its_days_requests_is_skipped_for_a_while(fake, monkeypatch):
    # The free tier allows a model a few requests a day. Once they are spent,
    # asking it first on every call only adds a failed round trip.
    monkeypatch.setattr(gemini_client.time, 'sleep', lambda s: None)
    models = fake({'first': DAILY})

    generate_json('x')
    generate_json('x')

    assert models.calls == ['first', 'second', 'second']


def test_a_per_minute_limit_is_tried_again_soon(fake, monkeypatch):
    # A minute's limit clears in a minute; it must not cost the hour.
    monkeypatch.setattr(gemini_client.time, 'sleep', lambda s: None)
    now = [1000.0]
    monkeypatch.setattr(gemini_client.time, 'monotonic', lambda: now[0])
    models = fake({'first': PER_MINUTE})

    generate_json('x')
    now[0] += 61
    generate_json('x')

    assert models.calls == ['first', 'second', 'first', 'second']
