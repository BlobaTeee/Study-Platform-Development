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


# ---- JSON hỏng thì thử model khác, đừng mất hẳn một đoạn nguồn -----------------------

def test_a_model_answering_with_prose_hands_over_to_the_next(fake, settings):
    # Gặp thật khi sinh: một đoạn nguồn trả về "Model returned invalid JSON" và
    # mất hẳn, dù chuỗi dự phòng còn model khác trả lời được.
    settings.GEMINI_THINKING = 'default'
    models = fake(script={'first': 'Chắc chắn rồi! Đây là các câu hỏi của bạn:'})

    assert generate_json('x') == {'questions': ['ok']}
    assert [model for model, _ in models.calls] == ['first', 'second']


def test_json_that_no_model_can_produce_is_still_reported_as_such(fake, settings):
    settings.GEMINI_THINKING = 'default'
    fake(script={'first': 'không phải JSON', 'second': 'cũng không phải JSON'})

    with pytest.raises(gemini_client.GeminiGenerationError, match='invalid JSON'):
        generate_json('x')


def test_bad_json_is_not_treated_as_the_model_being_down(fake, settings):
    # Trả lời sai định dạng không phải là model hỏng, nên đừng bỏ qua nó 5 phút.
    settings.GEMINI_THINKING = 'default'
    fake(script={'first': 'không phải JSON'})

    generate_json('x')

    assert gemini_client._in_cooldown('first') is False


# ---- hạn chờ do ta tự giữ, không phó cho server ---------------------------------------

def test_waiting_stops_at_our_own_deadline(settings):
    # Deadline gửi kèm request không chặn được mọi kiểu treo: một đoạn nguồn đã
    # ngồi 560s trong khi deadline đặt 30s, vì server giữ kết nối mở.
    settings.GEMINI_TIMEOUT_SECONDS = 10
    import time as _time

    started = _time.time()
    with pytest.raises(Exception, match='timed out'):
        gemini_client._call_with_deadline(lambda: _time.sleep(30), seconds=0.2)

    assert _time.time() - started < 2


def test_our_deadline_error_reads_as_transient():
    exc = None
    try:
        gemini_client._call_with_deadline(lambda: __import__('time').sleep(5), seconds=0.1)
    except Exception as e:
        exc = e
    assert gemini_client.is_transient_error(exc) is True


def test_a_fast_answer_passes_straight_through():
    assert gemini_client._call_with_deadline(lambda: 'xong', seconds=5) == 'xong'


def test_an_error_inside_the_call_is_raised_as_itself():
    def boom():
        raise ValueError('vỡ')

    with pytest.raises(ValueError, match='vỡ'):
        gemini_client._call_with_deadline(boom, seconds=5)


def test_a_model_that_never_answers_hands_over_to_the_next(fake, settings, monkeypatch):
    settings.GEMINI_THINKING = 'default'
    models = fake()
    import time as _time
    real = models.generate_content
    tried = []

    def slow(model, contents, config=None, **kwargs):
        tried.append(model)
        if model == 'first':
            _time.sleep(5)      # không bao giờ trả lời trong hạn
        return real(model, contents, config=config, **kwargs)

    monkeypatch.setattr(models, 'generate_content', slow)
    monkeypatch.setattr(gemini_client, '_wait_seconds', lambda quick=False: 0.2)

    started = _time.time()
    assert generate_json('x') == {'questions': ['ok']}

    assert tried == ['first', 'second']
    # Không chờ hết 5 giây của model treo.
    assert _time.time() - started < 2


def test_a_model_that_never_answers_is_not_waited_for_again(fake, settings, monkeypatch):
    settings.GEMINI_THINKING = 'default'
    settings.GEMINI_COOLDOWN_SECONDS = 300
    models = fake()
    import time as _time
    real = models.generate_content
    tried = []

    def slow(model, contents, config=None, **kwargs):
        tried.append(model)
        if model == 'first':
            _time.sleep(5)
        return real(model, contents, config=config, **kwargs)

    monkeypatch.setattr(models, 'generate_content', slow)
    monkeypatch.setattr(gemini_client, '_wait_seconds', lambda quick=False: 0.2)

    generate_json('x')
    generate_json('x')

    assert tried == ['first', 'second', 'second']
