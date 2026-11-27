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


def test_a_box_the_text_has_no_tag_for_is_dropped(client, monkeypatch):
    """A table copied as text also got a box, which landed on the next
    question's lines; shown and sent along, it mixed the two questions up."""
    class Reader:
        def generate_json_from_images(self, prompt, images):
            assert 'never a figure' in prompt
            return {'found': True, 'questions': [{'label': 'Câu 1', 'instruction': '',
                    'text': 'Cho bảng số liệu sau:\n[Table: Cặp oxi hóa - khử; E (V)]\na) Zn khử mạnh nhất.\nB) Fe2+ oxi hoá mạnh hơn Cu2+.',
                    'figures': [{'page': 1, 'box': [500, 200, 700, 400]}]}]}
    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: Reader())
    from django.core.files.uploadedfile import SimpleUploadedFile
    res = client.post('/api/exercises/read-photo/', {'image': SimpleUploadedFile('de.png', _page(), 'image/png')},
                      format='multipart')
    [question] = res.json()['questions']
    assert question['figures'] == []
    assert '\nb) Fe2+' in question['text']             # lettered like the first statement


def test_a_figure_described_without_its_tag_is_still_shown(client, monkeypatch):
    """The reader wrote "[Ellipse with ...]" for a paper's drawing, with its
    box but no "Figure 1:", and the test showed only the words (2026-11-26)."""
    class Reader:
        def generate_json_from_images(self, prompt, images):
            return {'found': True, 'questions': [{'label': 'Câu 20', 'instruction': '',
                    'text': 'Tính $S=a+b+c+d$. [Ellipse with semi-major axis and a cubic curve through the centre]',
                    'figures': [{'page': 1, 'box': [500, 200, 700, 400]}]}]}
    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: Reader())
    from django.core.files.uploadedfile import SimpleUploadedFile
    res = client.post('/api/exercises/read-photo/', {'image': SimpleUploadedFile('de.png', _page(), 'image/png')},
                      format='multipart')
    [question] = res.json()['questions']
    assert '[Figure 1: Ellipse with' in question['text']
    assert len(question['figures']) == 1 and question['figures'][0].startswith('data:image/png')


@pytest.mark.parametrize('text', ['Góc $[B,SC,D]$ bằng bao nhiêu độ, hỏi cả lớp xem?',
                                  'Cho bảng [Table: Cặp oxi hóa - khử; E (V) của từng cặp]',
                                  'Bảng biến thiên [On (-\\infty; -2): y giảm từ 1 xuống âm vô cùng]',
                                  'Đã có [Figure 1: hình] và [Một hình chữ nhật dài hơn chiều rộng nhiều]'])
def test_maths_tables_and_tagged_texts_are_left_alone(text):
    assert figures.tag_untagged(text, 1) == text


def test_a_figure_not_in_the_problem_is_not_sent_to_the_answer_key(monkeypatch):
    from exercises.services import problems
    [[url]] = figures.cut(_page(), 'image/png', [[(1, (0.5, 0.2, 0.7, 0.4))]])
    seen = {}

    class Model:
        def generate_json_from_images(self, prompt, images):
            seen['images'] = images
            return {'problems': []}

        def generate_json(self, prompt):
            seen['images'] = []
            return {'problems': []}
    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: Model())
    problems._set_rubrics(['Cho bảng số liệu sau: [Table: E (V)] a) Zn khử mạnh nhất.'], [[url]])
    assert seen['images'] == []


def test_a_set_keeps_each_problems_figures(client, monkeypatch):
    [[url]] = figures.cut(_page(), 'image/png', [[(1, (0.5, 0.2, 0.7, 0.4))]])
    from tests.test_exercises import RUBRIC
    one = {'complete': True, **RUBRIC, 'kind': 'written',
           'prompt': 'Công thức cấu tạo sau có trong thành phần chính của chất nào? [Figure 1: mạch carbon]'}

    class Model:
        def generate_json_from_images(self, prompt, images):
            assert 'keep each such tag exactly as\nwritten' in prompt
            assert len(images) == 1        # the cut figure; the broken one is not sent
            return {'problems': [one, one]}
    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: Model())
    texts = ['Công thức cấu tạo sau có trong thành phần chính của chất nào? [Figure 1: mạch carbon]'] * 2
    res = client.post('/api/exercises/own-set/', {'texts': texts, 'figures': [[url], ['data:image/png;base64,AAAA']]},
                      format='json')
    assert res.status_code == 201
    first, second = Exercise.objects.order_by('id')
    assert first.figures[0].startswith('data:image/png') and second.figures == [None]
    assert client.get(f'/api/exercises/{first.id}/').json()['figures'] == first.figures


# ---- a rough box moved onto the pictures placed on a PDF page ---------------------------

def _pdf_with_picture():
    """A 1000 x 1000 pt page with a 2 x 2 picture drawn at x 200-600, y 300-400
    from the top (in shares: ymin .3, xmin .2, ymax .4, xmax .6), and a
    full-page picture as a scan would have."""
    stream = b'q 1000 0 0 1000 0 0 cm /Scan Do Q q 400 0 0 100 200 600 cm /Fig Do Q'
    image = b'<< /Type /XObject /Subtype /Image /Width 2 /Height 2 /ColorSpace /DeviceGray ' \
            b'/BitsPerComponent 8 /Length 4 >>\nstream\n\x00\xff\xff\x00\nendstream'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 1000 1000] /Contents 4 0 R '
               b'/Resources << /XObject << /Fig 5 0 R /Scan 6 0 R >> >> >>',
               b'<< /Length %d >>\nstream\n' % len(stream) + stream + b'\nendstream',
               image, image]
    out, offsets = io.BytesIO(), []
    out.write(b'%PDF-1.4\n')
    for n, body in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(b'%d 0 obj\n' % n + body + b'\nendobj\n')
    xref = out.tell()
    out.write(b'xref\n0 %d\n0000000000 65535 f \n' % (len(objects) + 1))
    out.write(b''.join(b'%010d 00000 n \n' % o for o in offsets))
    out.write(b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objects) + 1, xref))
    return out.getvalue()


def test_pictures_placed_on_a_pdf_page_are_found():
    [scan, fig] = figures.placed_pictures(_pdf_with_picture(), {1})[1]
    assert scan == pytest.approx((0.0, 0.0, 1.0, 1.0))
    assert fig == pytest.approx((0.3, 0.2, 0.4, 0.6))


def test_a_rough_box_moves_onto_the_picture_it_covers():
    """The box took in the question's line above and cut off the right end."""
    pictures = figures.placed_pictures(_pdf_with_picture(), {1})[1]
    assert figures._snap((0.25, 0.15, 0.45, 0.5), pictures) == pytest.approx((0.3, 0.2, 0.4, 0.6))


def test_a_box_around_something_else_keeps_its_own_shape():
    pictures = figures.placed_pictures(_pdf_with_picture(), {1})[1]
    assert figures._snap((0.6, 0.1, 0.9, 0.9), pictures) is None     # a drawing; only the scan is there
    assert figures._snap((0.0, 0.0, 1.0, 1.0), [(0.3, 0.2, 0.31, 0.21)]) is None   # a speck in a big box
