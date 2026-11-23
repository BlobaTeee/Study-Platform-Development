"""Figures cut from an exam page and kept with the practice problem."""
import base64
import io

import pytest
from PIL import Image, ImageDraw

from exercises.models import Exercise
from exercises.services import figures

pytestmark = pytest.mark.django_db


def _page():
    """A 'page': white, with a black square at x 200-400, y 500-700 (thousandths)."""
    image = Image.new('RGB', (1000, 1000), 'white')
    ImageDraw.Draw(image).rectangle((200, 500, 400, 700), fill='black')
    out = io.BytesIO()
    image.save(out, 'PNG')
    return out.getvalue()


def _decode(url):
    return Image.open(io.BytesIO(base64.b64decode(url.split(',', 1)[1])))


def test_boxes_keep_order_and_drop_nonsense():
    item = {'figures': [{'page': 1, 'box': [500, 200, 700, 400]}, {'box': [700, 0, 100, 10]}, 'x',
                        {'page': 2, 'box': [0, 0, 1200, 1000]}]}
    boxes = figures.boxes_of(item)
    assert boxes[0] == (1, (0.5, 0.2, 0.7, 0.4))
    assert boxes[1] is None and boxes[2] is None
    assert boxes[3] == (2, (0.0, 0.0, 1.0, 1.0))        # clamped to the page


def test_a_figure_is_cut_from_a_photo_with_a_margin():
    [[url]] = figures.cut(_page(), 'image/png', [[(1, (0.5, 0.2, 0.7, 0.4))]])
    image = _decode(url)
    assert url.startswith('data:image/png;base64,')
    assert 230 <= image.width <= 250 and 240 <= image.height <= 260   # the box plus its margin
    assert image.getpixel((image.width // 2, image.height // 2)) == (0, 0, 0)


def test_a_box_too_small_or_a_page_not_there_gives_none():
    assert figures.cut(_page(), 'image/png', [[(1, (0.5, 0.5, 0.501, 0.501)), (3, (0, 0, 1, 1))], []]) == [[None, None], []]


def test_only_real_pictures_come_back_from_the_browser():
    [[url]] = figures.cut(_page(), 'image/png', [[(1, (0.5, 0.2, 0.7, 0.4))]])
    assert figures.clean(url).startswith('data:image/png;base64,')
    assert figures.clean('data:image/png;base64,' + base64.b64encode(b'<script>').decode()) is None
    assert figures.clean('https://example.com/x.png') is None
    assert figures.clean(None) is None


def test_reading_a_photo_returns_its_figures(client, monkeypatch):
    class Reader:
        def generate_json_from_images(self, prompt, images):
            return {'found': True, 'questions': [{'label': 'Câu 3', 'instruction': '',
                    'text': 'Công thức sau là gì?\n[Figure 1: mạch carbon]\nA. Xà phòng.\nB. Giấm.',
                    'figures': [{'page': 1, 'box': [500, 200, 700, 400]}]}]}
    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: Reader())
    from django.core.files.uploadedfile import SimpleUploadedFile
    res = client.post('/api/exercises/read-photo/', {'image': SimpleUploadedFile('de.png', _page(), 'image/png')},
                      format='multipart')
    assert res.status_code == 200
    [question] = res.json()['questions']
    assert len(question['figures']) == 1 and question['figures'][0].startswith('data:image/png')


def test_a_set_keeps_each_problems_figures(client, monkeypatch):
    [[url]] = figures.cut(_page(), 'image/png', [[(1, (0.5, 0.2, 0.7, 0.4))]])
    from tests.test_exercises import RUBRIC
    one = {'complete': True, **RUBRIC, 'kind': 'written',
           'prompt': 'Công thức cấu tạo sau có trong thành phần chính của chất nào? [Figure 1: mạch carbon]'}

    class Model:
        def generate_json(self, prompt):
            assert 'keep each such tag exactly as written' in prompt
            return {'problems': [one, one]}
    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: Model())
    texts = ['Công thức cấu tạo sau có trong thành phần chính của chất nào? [Figure 1: mạch carbon]'] * 2
    res = client.post('/api/exercises/own-set/', {'texts': texts, 'figures': [[url], ['data:image/png;base64,AAAA']]},
                      format='json')
    assert res.status_code == 201
    first, second = Exercise.objects.order_by('id')
    assert first.figures[0].startswith('data:image/png') and second.figures == [None]
    assert client.get(f'/api/exercises/{first.id}/').json()['figures'] == first.figures
