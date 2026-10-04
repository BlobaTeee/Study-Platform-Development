"""Sinh trên nhiều đoạn nguồn cùng lúc, nhưng kết quả phải y như chạy lần lượt.

Mỗi đoạn là một lời gọi model mất vài giây, và trước đây chúng chạy nối tiếp:
ba đoạn là ba lần chờ. Chạy song song thì nhanh gấp mấy lần, nhưng chỉ đúng khi
thứ tự câu hỏi không phụ thuộc vào đoạn nào trả lời trước.
"""
import threading
import time

import pytest

from notebooks.services.generate import _generate_over_chunks


class _Provider:
    """Model giả: mỗi đoạn trả về một câu hỏi, có thể chậm hoặc lỗi."""

    def __init__(self, *, delays=None, errors=(), text=None):
        self.delays = delays or {}
        self.errors = set(errors)
        self.text = text or (lambda chunk: chunk)
        self.live = 0
        self.most_at_once = 0
        self._lock = threading.Lock()

    def generate_json(self, prompt):
        with self._lock:
            self.live += 1
            self.most_at_once = max(self.most_at_once, self.live)
        try:
            chunk = prompt.rsplit('|', 1)[-1]
            time.sleep(self.delays.get(chunk, 0))
            if chunk in self.errors:
                raise RuntimeError(f'đoạn {chunk} lỗi')
            return {'questions': [{'question_text': self.text(chunk)}]}
        finally:
            with self._lock:
                self.live -= 1


def build_prompt(chunk, n):
    return f'sinh {n} câu|{chunk}'


def run(provider, chunks, per_chunk=1, limit=10):
    return _generate_over_chunks(provider, chunks, per_chunk, build_prompt, 'questions', limit)


def test_the_slowest_excerpt_does_not_jump_the_queue():
    # Đoạn 'a' trả lời chậm nhất, nhưng câu của nó vẫn phải đứng đầu.
    provider = _Provider(delays={'a': 0.15, 'b': 0.05, 'c': 0.0})

    items = run(provider, ['a', 'b', 'c'])

    assert [i['question_text'] for i in items] == ['a', 'b', 'c']


def test_every_excerpt_keeps_the_passage_it_came_from():
    provider = _Provider(delays={'a': 0.1})

    items = run(provider, ['a', 'b'])

    assert [i['_excerpt'] for i in items] == ['a', 'b']


def test_one_failing_excerpt_does_not_sink_the_others():
    provider = _Provider(errors={'b'})

    items = run(provider, ['a', 'b', 'c'])

    assert [i['question_text'] for i in items] == ['a', 'c']


def test_all_excerpts_failing_still_raises():
    provider = _Provider(errors={'a', 'b'})

    with pytest.raises(RuntimeError):
        run(provider, ['a', 'b'])


def test_duplicate_questions_across_excerpts_are_dropped_once():
    provider = _Provider(text=lambda chunk: 'cùng một câu')

    items = run(provider, ['a', 'b', 'c'])

    assert len(items) == 1


def test_calls_run_at_the_same_time():
    provider = _Provider(delays={c: 0.1 for c in 'abc'})

    started = time.time()
    run(provider, ['a', 'b', 'c'])

    # Nối tiếp là 0,3s; song song thì quanh 0,1s.
    assert time.time() - started < 0.25
    assert provider.most_at_once > 1


def test_no_more_calls_at_once_than_the_configured_limit(settings):
    # Bắn hết cùng lúc là cách nhanh nhất để ăn 429 của nhà cung cấp.
    settings.GENERATE_CONCURRENCY = 2
    provider = _Provider(delays={c: 0.05 for c in 'abcdef'})

    run(provider, list('abcdef'))

    assert provider.most_at_once <= 2


def test_one_excerpt_needs_no_threads():
    provider = _Provider()

    items = run(provider, ['a'])

    assert [i['question_text'] for i in items] == ['a']
    assert provider.most_at_once == 1
