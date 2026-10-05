"""A document overview starts with the document, not with the model talking.

Two of the four stored overviews began "Here is a summary of the study in 2-3
sentences:" — the model's preamble, shown to the student as if it were part
of the overview.
"""
import pytest

from notebooks.models import Source
from notebooks.services.textnorm import clean_summary
from tests.conftest import make_source


@pytest.mark.parametrize('raw, expected', [
    ('Here is a summary of the study in 2-3 sentences:  This article examines policy.',
     'This article examines policy.'),
    ('Here is a 3-sentence study overview: CityHelp is a mobile prototype.',
     'CityHelp is a mobile prototype.'),
    ("Sure! Here's a summary: The lecture covers design.", 'The lecture covers design.'),
    ('Certainly. Here is a brief overview:\nThe paper studies grading.', 'The paper studies grading.'),
    ('Đây là bản tóm tắt ngắn: Bài giảng nói về thiết kế.', 'Bài giảng nói về thiết kế.'),
    ('Dưới đây là phần tổng quan: Tài liệu bàn về AI.', 'Tài liệu bàn về AI.'),
])
def test_the_models_preamble_is_removed(raw, expected):
    assert clean_summary(raw) == expected


@pytest.mark.parametrize('text', [
    'The lecture introduces interaction design: users come first.',
    'Here, the authors argue that grading should be automated.',
    'Here is where the study departs from earlier work, without any colon at all.',
    '',
])
def test_a_real_overview_is_left_alone(text):
    assert clean_summary(text) == text


def test_a_preamble_with_nothing_after_it_is_kept_rather_than_blanked():
    assert clean_summary('Here is a summary:') == 'Here is a summary:'


@pytest.mark.django_db
def test_stored_overviews_are_served_clean(client, notebook):
    # Rows written before the fix are cleaned on the way out, without
    # rewriting what is stored.
    source = notebook.sources.first()
    Source.objects.filter(pk=source.pk).update(
        gemini_summary='Here is a 3-sentence study overview: Cells divide.')

    detail = client.get(f'/api/notebooks/sources/{source.id}/').json()
    listed = client.get(f'/api/notebooks/notebooks/{notebook.id}/').json()

    assert detail['gemini_summary'] == 'Cells divide.'
    assert {s['id']: s['gemini_summary'] for s in listed['sources']}[source.id] == 'Cells divide.'
    assert Source.objects.get(pk=source.pk).gemini_summary.startswith('Here is')
