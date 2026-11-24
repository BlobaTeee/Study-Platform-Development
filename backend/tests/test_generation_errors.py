"""A failed generation tells the student what to do, in their language.

On 2026-11-24 the page showed "Quiz generation failed: Every Gemini model was
busy: 503 UNAVAILABLE. {'error': {'code': 503, ...}}" word for word.
"""
import pytest

from notebooks.services.gemini_client import GeminiGenerationError, GeminiQuotaError

pytestmark = pytest.mark.django_db

BUSY = ("Quiz generation failed: Every Gemini model was busy: 503 UNAVAILABLE. {'error': {'code': 503, "
        "'message': 'This model is currently experiencing high demand.', 'status': 'UNAVAILABLE'}}")


@pytest.mark.parametrize('error, words', [
    (GeminiGenerationError(BUSY), 'AI đang quá tải'),
    (GeminiQuotaError('429 RESOURCE_EXHAUSTED'), 'hết lượt'),
    (GeminiGenerationError('Every Gemini model was busy: Model timed out after 30s'), 'quá lâu'),
    (GeminiGenerationError('Quiz generation failed: bad JSON'), 'Thử lại'),
])
def test_a_providers_error_reaches_the_page_as_what_to_do(client, notebook, monkeypatch, error, words):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr('notebooks.views.generate_quiz_for_sources', fail)
    ids = list(notebook.sources.values_list('id', flat=True))
    res = client.post(f'/api/notebooks/notebooks/{notebook.id}/generate_quiz/', {'source_ids': ids},
                      format='json', HTTP_ACCEPT_LANGUAGE='vi')
    detail = res.json()['detail']
    assert res.status_code == 400 and words in detail
    assert '503' not in detail and 'Gemini' not in detail and '{' not in detail
