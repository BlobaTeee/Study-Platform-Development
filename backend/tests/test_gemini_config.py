"""Yêu cầu JSON và mức suy nghĩ — kèm đường lùi khi model không nhận.

Token đo được cho thấy phần "suy nghĩ" của model chiếm quá nửa lượng token mỗi
lần sinh (2.089 nghĩ so với 765 trả lời trên gemini-2.5-flash), nên hạ nó là
cách giảm token hiệu quả nhất. Nhưng tham số điều khiển việc đó khác nhau giữa
các dòng model: gemini-2.5-flash trả 400 INVALID_ARGUMENT khi nhận
`thinking_level` của dòng 3.x. Một model dự phòng không được chết vì lý do đó.
"""
import pytest

from notebooks.services import gemini_client
from notebooks.services.gemini_client import generate_json


class _Models:
    """Model giả ghi lại cấu hình nó nhận được."""

    def __init__(self, reject=(), script=None):
        self.reject = set(reject)       # model trả 400 khi có thinking_config
        self.script = script or {}
        self.calls = []                 # [(model, config)]

    def generate_content(self, model, contents, config=None, **kwargs):
        self.calls.append((model, config))
        thinking = getattr(config, 'thinking_config', None)
        if model in self.reject and thinking is not None:
            raise Exception("400 INVALID_ARGUMENT. Thinking level is not supported")
        outcome = self.script.get(model, '{"questions": ["ok"]}')
        if isinstance(outcome, Exception):
            raise outcome
        return type('R', (), {'text': outcome})()


@pytest.fixture
def fake(monkeypatch, settings):
    settings.GEMINI_MODEL = 'first'
    settings.GEMINI_MODEL_FALLBACKS = 'second'

    def install(**kwargs):
        models = _Models(**kwargs)
        monkeypatch.setattr(gemini_client, '_get_client',
                            lambda: type('C', (), {'models': models})())
        return models
    return install


def test_json_is_requested_not_just_asked_for_in_the_prompt(fake, settings):
    settings.GEMINI_THINKING = 'default'
    models = fake()

    generate_json('x')

    _, config = models.calls[0]
    assert config.response_mime_type == 'application/json'


def test_thinking_is_turned_off_when_configured(fake, settings):
    settings.GEMINI_THINKING = 'off'
    models = fake()

    generate_json('x')

    _, config = models.calls[0]
    assert config.thinking_config.thinking_budget == 0


def test_default_leaves_the_model_to_decide(fake, settings):
    settings.GEMINI_THINKING = 'default'
    models = fake()

    generate_json('x')

    _, config = models.calls[0]
    assert config.thinking_config is None


def test_a_model_that_rejects_the_thinking_setting_is_retried_without_it(fake, settings):
    # 2.5-flash từ chối tham số của dòng 3.x. Nó vẫn phải sinh được, chứ không
    # bị bỏ qua để rơi xuống model sau.
    settings.GEMINI_THINKING = 'low'
    models = fake(reject={'first'})

    assert generate_json('x') == {'questions': ['ok']}
    assert [model for model, _ in models.calls] == ['first', 'first']
    assert models.calls[1][1].thinking_config is None


def test_the_retry_keeps_asking_for_json(fake, settings):
    settings.GEMINI_THINKING = 'low'
    models = fake(reject={'first'})

    generate_json('x')

    assert models.calls[1][1].response_mime_type == 'application/json'


def test_a_broken_model_still_hands_over_to_the_next(fake, settings):
    settings.GEMINI_THINKING = 'off'
    models = fake(script={'first': Exception('503 UNAVAILABLE. overloaded')})

    assert generate_json('x') == {'questions': ['ok']}
    assert [model for model, _ in models.calls] == ['first', 'second']


# ---- không chờ mãi một model đang treo -----------------------------------------------

def test_the_client_is_given_a_deadline(monkeypatch, settings):
    # Không đặt timeout thì một model quá tải làm người dùng chờ vô hạn: lần đo
    # gemini-3.8-flash hôm nay treo hơn 30 phút mà không trả lỗi nào.
    settings.GEMINI_API_KEY = 'k'
    settings.GEMINI_TIMEOUT_SECONDS = 25
    seen = {}

    class _Client:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(gemini_client, '_genai_client_class', lambda: _Client)

    gemini_client._get_client()

    assert seen['http_options'].timeout == 25_000   # SDK tính bằng mili-giây


@pytest.mark.parametrize('message', [
    'ReadTimeout: timed out',
    '504 DEADLINE_EXCEEDED',
    'Request timed out after 25s',
])
def test_a_timeout_counts_as_transient_so_the_next_model_is_tried(message):
    assert gemini_client.is_transient_error(Exception(message)) is True


def test_a_hanging_model_hands_over_instead_of_failing(fake, settings):
    settings.GEMINI_THINKING = 'default'
    models = fake(script={'first': Exception('ReadTimeout: timed out')})

    assert generate_json('x') == {'questions': ['ok']}
    assert [model for model, _ in models.calls] == ['first', 'second']


def test_a_deadline_below_the_server_minimum_is_raised_to_it(monkeypatch, settings):
    # Gemini trả 400 cho deadline dưới 10s ("Minimum allowed deadline is 10s"),
    # và 400 không phải lỗi tạm thời — nên một cấu hình quá ngắn sẽ làm chết cả
    # lượt sinh thay vì chỉ chậm.
    settings.GEMINI_API_KEY = 'k'
    settings.GEMINI_TIMEOUT_SECONDS = 3
    seen = {}

    class _Client:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr(gemini_client, '_genai_client_class', lambda: _Client)

    gemini_client._get_client()

    assert seen['http_options'].timeout == 10_000
