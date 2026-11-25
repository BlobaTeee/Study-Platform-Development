"""A photographed problem read into text the student checks before it is used.

The photo is read once (one request) and thrown away; only the text comes
back, maths in LaTeX so the page can show it as it was printed. A photo of a
whole exam page comes back as its questions, one each, so the student picks
the one to practise. Nothing is saved until the student creates the problem.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from exercises.models import Exercise

pytestmark = pytest.mark.django_db
URL = '/api/exercises/read-photo/'
JPEG = b'\xff\xd8\xff\xe0' + b'\x00' * 200
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 200


class Reader:
    name = 'gemini'

    def __init__(self, reply):
        self.reply = reply
        self.images = None

    def generate_json(self, prompt):
        raise AssertionError('a photo must be read with the image')

    def generate_json_from_images(self, prompt, images):
        self.images = images
        self.prompt = prompt
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.fixture
def reader(monkeypatch):
    def use(reply):
        r = Reader(reply)
        monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: r)
        return r
    return use


def _post(client, data, name='problem.jpg', ctype='image/jpeg'):
    return client.post(URL, {'image': SimpleUploadedFile(name, data, content_type=ctype)}, format='multipart')


def _one(text, label='Câu 1'):
    return {'found': True, 'questions': [{'label': label, 'text': text}]}


def test_the_problem_comes_back_as_text_with_maths_in_latex(client, reader):
    r = reader(_one(r'Tính $\int_0^1 x^2\,dx$.'))

    res = _post(client, JPEG)

    assert res.status_code == 200
    assert res.json()['questions'] == [{'label': 'Câu 1', 'instruction': '', 'text': r'Tính $\int_0^1 x^2\,dx$.', 'kind': 'written', 'figures': []}]
    assert r.images == [(JPEG, 'image/jpeg')]
    assert 'LaTeX' in r.prompt
    assert not Exercise.objects.exists()          # nothing saved until the student creates it


def test_an_exam_page_comes_back_as_its_questions_in_order(client, reader):
    reader({'found': True, 'questions': [
        {'label': 'Câu 7', 'text': 'Cho cấp số cộng $(u_n)$ với $u_1 = 2$, $d = 3$. Tính $u_5$.'},
        {'label': 'Câu 8', 'text': ''},                                  # nothing in it: dropped
        {'label': 'Câu 10', 'text': 'Cho hàm số $y = \\frac{ax+b}{cx+d}$ ...'},
        'not a question',
    ]})

    res = _post(client, JPEG)

    assert [q['label'] for q in res.json()['questions']] == ['Câu 7', 'Câu 10']


def test_the_paper_comes_back_with_a_short_name_for_its_set(client, reader):
    r = reader({**_one('Tính $u_5$.'), 'title': '  Đề ôn tập cuối kỳ 1\n Hoá học 12 '})
    res = _post(client, JPEG)
    assert res.json()['title'] == 'Đề ôn tập cuối kỳ 1 Hoá học 12'
    reader({**_one('Tính $u_5$.'), 'title': 'ĐỀ KIỂM TRA CUỐI KỲ I MÔN HÓA HỌC 12'})   # a heading in capitals
    assert _post(client, JPEG).json()['title'] == 'Đề kiểm tra cuối kỳ I môn hóa học 12'
    assert '"title"' in r.prompt
    reader(_one('Tính $u_5$.'))                      # none given: the file's name is used
    assert _post(client, JPEG).json()['title'] == ''


def test_every_question_carries_its_part_when_the_paper_has_several(client, reader):
    """The model used to add the part only once the numbering restarted,
    so Part I's questions came back bare and Part II's as "PHẦN II · Câu 1"."""
    reader({'found': True, 'questions': [
        {'label': 'Câu 11', 'part': 'PHẦN I', 'text': 'Đồ thị dưới đây là của hàm số nào?'},
        {'label': 'Câu 12', 'text': 'Cho hàm số $y = x$. Mệnh đề nào đúng?'},          # no part: Part I's
        {'label': 'PHẦN II · Câu 1', 'part': 'PHẦN II.', 'text': 'Cho hàm số $f(x) = x^3$.'},
        # The whole heading, as the model gave it on 2026-11-23: the name and number are kept.
        {'label': 'Câu 1', 'part': 'Phần Iii. Câu trắc nghiệm trả lời ngắn', 'text': 'Có 9 người cùng lên 3 toa tàu.'},
    ]})
    labels = [q['label'] for q in _post(client, JPEG).json()['questions']]
    assert labels == ['Phần I · Câu 11', 'Phần I · Câu 12', 'Phần II · Câu 1', 'Phần III · Câu 1']


def test_a_paper_with_one_part_keeps_plain_labels(client, reader):
    reader({'found': True, 'questions': [{'label': 'Câu 1', 'part': 'PHẦN I', 'text': 'Tính $1 + 1$.'},
                                         {'label': 'Câu 2', 'part': 'PHẦN I', 'text': 'Tính $2 + 2$.'}]})
    assert [q['label'] for q in _post(client, JPEG).json()['questions']] == ['Câu 1', 'Câu 2']


def test_a_key_read_from_a_picture_comes_back_as_a_hint_only(client, reader):
    """Read from a picture the key can be misread (7 of 28 on 2026-11-24),
    so it is never handed over as the paper's answer."""
    r = reader({'found': True, 'questions': [
        {'label': 'Câu 1', 'text': 'Cặp nào có tính khử mạnh nhất? A. Na. B. Li.', 'answer': 'B'},
        {'label': 'Câu 2', 'text': 'Cho bảng. a) Zn khử mạnh. b) Fe oxi hoá mạnh.', 'answer': {'a': 'Đ', 'b': 'S'}},
        {'label': 'Câu 3', 'text': 'Phân tử khối của Y?', 'answer': 180},
        {'label': 'Câu 4', 'text': 'Giải thích vì sao.', 'answer': None},
        {'label': 'Câu 5', 'text': 'Cho bảng. a) Zn. b) Fe.', 'answer': {'a': 'maybe'}},
    ]})
    questions = _post(client, JPEG).json()['questions']
    assert [q.get('hint') for q in questions] == ['B', {'a': True, 'b': False}, '180', None, None]
    assert all('answer' not in q for q in questions)
    assert 'ĐÁP ÁN' in r.prompt and 'handwriting' in r.prompt


def test_a_question_without_a_label_is_numbered(client, reader):
    reader({'found': True, 'questions': [{'text': 'Solve $x + 1 = 3$.'}, {'label': '  ', 'text': 'Find $x$.'}]})
    assert [q['label'] for q in _post(client, JPEG).json()['questions']] == ['1', '2']


def test_a_reply_with_one_text_still_works(client, reader):
    reader({'found': True, 'text': 'Solve $x + 1 = 3$ for $x$.'})
    assert _post(client, JPEG).json()['questions'] == [{'label': '1', 'instruction': '', 'text': 'Solve $x + 1 = 3$ for $x$.', 'kind': 'written', 'figures': []}]


def test_the_reader_is_told_what_not_to_copy(client, reader):
    r = reader(_one('Solve x + 1 = 3 for x.'))
    _post(client, JPEG)
    prompt = r.prompt.lower()
    assert 'handwrit' in prompt                    # a circled answer would give the answer away
    assert 'variation table' in prompt and 'arrow' in prompt
    assert 'exactly as printed' in prompt          # n_2 stays n_2
    assert '"part"' in prompt                      # Part II's question 1 is not Part I's
    assert 'same language as the problem' in prompt  # a Vietnamese problem gets Vietnamese [notes]


def test_the_type_is_read_from_the_bytes_not_the_name(client, reader):
    r = reader(_one('Solve x + 1 = 3 for x.'))
    _post(client, PNG, name='photo.jpg', ctype='image/jpeg')
    assert r.images[0][1] == 'image/png'


def test_a_photo_without_a_problem_says_so(client, reader):
    reader({'found': False, 'questions': []})
    res = _post(client, JPEG)
    assert res.status_code == 400 and res.json()['no_problem'] is True


def test_something_that_is_not_an_image_pdf_or_word_is_refused_without_a_request(client, reader):
    r = reader({'found': True, 'text': 'x'})
    res = _post(client, b'Just some notes, not a picture', name='notes.txt', ctype='text/plain')
    assert res.status_code == 400 and r.images is None


def test_a_photo_that_is_too_large_is_refused(client, reader, settings):
    settings.PROBLEM_PHOTO_MAX_BYTES = 100
    r = reader({'found': True, 'text': 'x'})
    res = _post(client, JPEG)
    assert res.status_code == 400 and r.images is None


def test_no_file_is_a_400(client, reader):
    reader({'found': True, 'text': 'x'})
    assert client.post(URL, {}, format='multipart').status_code == 400


def test_a_failed_read_is_503_and_says_to_retry(client, reader):
    reader(RuntimeError('429 RESOURCE_EXHAUSTED quota'))
    res = _post(client, JPEG)
    assert res.status_code == 503 and 'free requests' in res.json()['detail']
    assert 'what you wrote' not in res.json()['detail']


def test_a_provider_that_cannot_read_images_is_503(client, monkeypatch):
    class TextOnly:
        name = 'custom_model'

        def generate_json_from_images(self, prompt, images):
            raise NotImplementedError('custom_model cannot read images')

    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: TextOnly())
    assert _post(client, JPEG).status_code == 503


def test_a_stranger_must_be_signed_in(db):
    from rest_framework.test import APIClient
    res = APIClient(HTTP_HOST='localhost').post(URL, {}, format='multipart')
    assert res.status_code in (401, 403)


def test_a_sections_instruction_comes_apart_from_the_question(client, reader):
    reader({'found': True, 'questions': [
        {'label': 'Câu 1', 'instruction': 'Trong mỗi ý a), b), c), d), chọn đúng hoặc sai.', 'text': 'Cho hàm số $f(x) = x^3$.'},
        {'label': 'Câu 2', 'text': 'Tính $2 + 2$.'},
    ]})
    first, second = _post(client, JPEG).json()['questions']
    assert first['instruction'].startswith('Trong mỗi ý') and first['text'] == 'Cho hàm số $f(x) = x^3$.'
    assert second['instruction'] == ''


# ---- files: a PDF goes as it is, a Word file as its text ---------------------------------

class TextReader(Reader):
    """Takes a text request too: what a Word file is sent as."""

    def generate_json(self, prompt):
        self.prompt = prompt
        return self.reply


def _docx(paragraphs):
    import io
    from docx import Document
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def test_a_pdf_is_read_like_a_photo(client, reader):
    r = reader(_one('Câu 1. Tính $2+2$.'))
    res = _post(client, b'%PDF-1.7\n' + b'0' * 200, name='de-thi.pdf', ctype='application/pdf')
    assert res.status_code == 200
    assert r.images[0][1] == 'application/pdf'


@pytest.fixture
def no_libreoffice(monkeypatch):
    monkeypatch.setattr('exercises.services.photo.soffice', lambda: None)


def test_a_word_file_goes_as_a_pdf_when_libreoffice_is_there(client, reader, monkeypatch):
    """ChemDraw and MathType objects are metafiles the model cannot read;
    drawn into a PDF they reach it as on paper."""
    monkeypatch.setattr('exercises.services.photo.docx_to_pdf', lambda data: b'%PDF-1.7 drawn')
    r = reader(_one('Câu 3. Công thức cấu tạo sau có trong thành phần chính của?'))
    res = _post(client, _docx(['Câu 3.']), name='de.docx',
                ctype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    assert res.status_code == 200
    assert r.images == [(b'%PDF-1.7 drawn', 'application/pdf')]


def test_without_libreoffice_a_word_file_is_read_as_text():
    from exercises.services import photo
    from unittest import mock
    with mock.patch.object(photo, 'soffice', return_value=None):
        assert photo.docx_to_pdf(_docx(['Câu 1.'])) is None


@pytest.mark.usefixtures('no_libreoffice')
def test_a_word_file_is_sent_as_its_text(client, monkeypatch):
    r = TextReader(_one('Tính diện tích hình vuông cạnh 3 cm.'))
    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: r)
    data = _docx(['Đề kiểm tra 15 phút', 'Câu 1. Tính diện tích hình vuông cạnh 3 cm.'])
    res = _post(client, data, name='de.docx',
                ctype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    assert res.status_code == 200
    assert r.images is None
    assert 'hình vuông cạnh 3 cm' in r.prompt


def _png(size=40):
    import io
    from PIL import Image
    out = io.BytesIO()
    Image.effect_noise((size, size), 60).convert('RGB').save(out, 'PNG')
    return out.getvalue()


@pytest.mark.usefixtures('no_libreoffice')
def test_a_word_file_sends_its_pictures_where_they_stand(client, monkeypatch):
    """A structural formula pasted as a picture reaches the model, marked in
    the text where the question shows it; the options in a table stay under
    their question."""
    import io
    from docx import Document
    r = TextReader(_one('x'))
    r.generate_json_from_images = lambda prompt, images: (setattr(r, 'prompt', prompt),
                                                          setattr(r, 'images', images), r.reply)[-1]
    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: r)
    doc = Document()
    doc.add_paragraph('Câu 3. Công thức cấu tạo sau có trong thành phần chính của?')
    doc.add_paragraph().add_run().add_picture(io.BytesIO(_png()))
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = 'A. Xà phòng.', 'B. Chất giặt rửa tổng hợp.'
    doc.add_paragraph('Câu 4. Câu sau.')
    out = io.BytesIO()
    doc.save(out)
    res = _post(client, out.getvalue(), name='de.docx',
                ctype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    assert res.status_code == 200
    assert len(r.images) == 1 and r.images[0][1] == 'image/png'
    body = r.prompt.split('The document, as text:')[1]
    assert body.index('Câu 3') < body.index('[Picture 1]') < body.index('A. Xà phòng.') < body.index('Câu 4')
    assert 'attached as 1 images' in r.prompt


def test_unreadable_word_pictures_are_marked_not_sent():
    from exercises.services.photo import _as_sendable
    assert _as_sendable(b'\x01\x00\x00\x00' + b'0' * 400) is None      # an EMF metafile
    assert _as_sendable(b'\x89PNG') == 'tiny'
    assert _as_sendable(_png())[1] == 'image/png'


@pytest.mark.usefixtures('no_libreoffice')
def test_an_empty_word_file_has_no_problem(client, monkeypatch):
    r = TextReader(_one('x'))
    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: r)
    res = _post(client, _docx([]), name='trong.docx', ctype='application/octet-stream')
    assert res.status_code == 400 and res.json()['no_problem'] is True


def test_the_reader_keeps_a_true_false_question_together(client, reader):
    r = reader(_one('x'))
    _post(client, JPEG)
    assert 'Never split a' in r.prompt and 'statements a), b), c), d)' in r.prompt


class Flaky(Reader):
    """Drops the connection on the first request, then answers."""

    def __init__(self, reply, failures):
        super().__init__(reply)
        self.failures = list(failures)
        self.calls = 0

    def generate_json_from_images(self, prompt, images):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return super().generate_json_from_images(prompt, images)


@pytest.fixture
def no_pause(monkeypatch):
    monkeypatch.setattr('exercises.services.common.RETRY_PAUSE_SECONDS', 0)


def test_a_dropped_connection_is_tried_once_more(client, monkeypatch, no_pause):
    r = Flaky(_one('Tính $2+2$.'), [ConnectionResetError(54, 'Connection reset by peer')])
    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: r)
    res = _post(client, JPEG)
    assert res.status_code == 200 and r.calls == 2


def test_a_connection_that_drops_twice_says_the_problems_could_not_be_read(client, monkeypatch, no_pause):
    drop = lambda: OSError('[Errno 54] Connection reset by peer')
    r = Flaky(_one('x'), [drop(), drop()])
    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: r)
    res = _post(client, JPEG)
    assert res.status_code == 503 and r.calls == 2
    assert 'could not be read' in res.json()['detail']
    assert 'what you wrote' not in res.json()['detail']


def test_a_refused_read_is_not_tried_again(client, monkeypatch, no_pause):
    r = Flaky(_one('x'), [RuntimeError('400 INVALID_ARGUMENT')])
    monkeypatch.setattr('notebooks.services.ai_provider.get_ai_provider', lambda: r)
    assert _post(client, JPEG).status_code == 503 and r.calls == 1


def test_a_bare_list_of_questions_is_read_as_the_questions(client, reader):
    reader([{'label': 'Câu 1', 'instruction': '', 'text': 'Tính $2+2$.'},
            {'label': 'Câu 2', 'instruction': '', 'text': 'Tính $3+3$.'}])
    res = _post(client, b'%PDF-1.7\n' + b'0' * 200, name='de.pdf', ctype='application/pdf')
    assert res.status_code == 200
    assert [q['label'] for q in res.json()['questions']] == ['Câu 1', 'Câu 2']


def test_an_overloaded_model_says_so_rather_than_too_slow(client, reader):
    reader(RuntimeError('Every Gemini model was busy: 503 UNAVAILABLE. This model is currently overloaded.'))
    res = _post(client, JPEG)
    assert res.status_code == 503 and 'overloaded' in res.json()['detail']


def test_reading_asks_for_little_thinking(settings, monkeypatch):
    from notebooks.services import gemini_client
    from notebooks.services.model_lane import long_read
    seen = []
    monkeypatch.setattr(gemini_client, '_request_config', lambda thinking=None: seen.append(thinking))
    monkeypatch.setattr(gemini_client, '_worth_trying', lambda models: [])
    settings.GEMINI_READ_THINKING = 'low'
    with long_read():
        try:
            gemini_client.generate_json('x')
        except Exception:
            pass
    assert seen == ['low']


def _keyed_docx():
    """A three-part paper's key laid out as the 2026-11-24 Hoá paper's:
    1..18 over letters, then 1a..4d over Đ/S beside 1..6 over numbers."""
    import io
    from docx import Document
    doc = Document()
    doc.add_paragraph('ĐÁP ÁN')
    first = doc.add_table(rows=2, cols=3)
    for i, (head, value) in enumerate([('1', 'B'), ('2', 'D'), ('3', 'C')]):
        first.cell(0, i).text, first.cell(1, i).text = head, value
    second = doc.add_table(rows=2, cols=6)
    for i, (head, value) in enumerate([('1a', 'D'), ('1b', 'S'), ('2a', 'S'), ('2b', 'Đ'), ('1', '1246'), ('2', '-0,7')]):
        second.cell(0, i).text, second.cell(1, i).text = head, value
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def test_a_word_files_key_is_read_from_its_table_not_the_model(client, reader, monkeypatch):
    monkeypatch.setattr('exercises.services.photo.docx_to_pdf', lambda data: b'%PDF-1.7 drawn')
    monkeypatch.setattr('exercises.services.figures.cut', lambda data, mime, boxes: [[] for _ in boxes])
    reader({'found': True, 'questions': [
        {'label': 'Câu 1', 'part': 'PHẦN I', 'text': 'A?', 'answer': 'A'},
        {'label': 'Câu 3', 'part': 'PHẦN I', 'text': 'C?', 'answer': 'C'},
        {'label': 'Câu 2', 'part': 'PHẦN II', 'text': 'a) x. b) y.', 'answer': {'a': True, 'b': False}},
        {'label': 'Câu 1', 'part': 'PHẦN III', 'text': 'M?', 'answer': '124'},
        {'label': 'Câu 2', 'part': 'PHẦN III', 'text': 'E?', 'answer': '-0,74'},
    ]})
    res = _post(client, _keyed_docx(), name='de.docx',
                ctype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    questions = res.json()['questions']
    assert [q.get('answer') for q in questions] == ['B', 'C', {'a': False, 'b': True}, '1246', '-0,7']


def test_a_key_that_does_not_fit_the_paper_is_not_used(client, reader, monkeypatch):
    """Two runs of numbers for a one-part paper: which run is whose cannot be
    told, so nothing is taken from it."""
    monkeypatch.setattr('exercises.services.photo.docx_to_pdf', lambda data: b'%PDF-1.7 drawn')
    monkeypatch.setattr('exercises.services.figures.cut', lambda data, mime, boxes: [[] for _ in boxes])
    reader({'found': True, 'questions': [{'label': 'Câu 1', 'text': 'A?', 'answer': 'A'}]})
    res = _post(client, _keyed_docx(), name='de.docx',
                ctype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    assert [(q.get('answer'), q.get('hint')) for q in res.json()['questions']] == [(None, 'A')]


def test_a_key_is_read_from_upright_tables_and_ignores_other_tables():
    import io
    from docx import Document
    from exercises.services.answer_key import key_from_docx
    doc = Document()
    options = doc.add_table(rows=1, cols=2)
    options.cell(0, 0).text, options.cell(0, 1).text = 'A. 1.', 'B. 3.'
    data = doc.add_table(rows=2, cols=3)
    for i, (head, value) in enumerate([('t (phút)', '0'), ('10', '20'), ('30', '40')]):
        data.cell(0, i).text, data.cell(1, i).text = head, value
    key = doc.add_table(rows=3, cols=2)
    for r, (head, value) in enumerate([('Câu', 'Đáp án'), ('1', 'b'), ('2', 'A')]):
        key.cell(r, 0).text, key.cell(r, 1).text = head, value
    out = io.BytesIO()
    doc.save(out)
    assert key_from_docx(out.getvalue()) == [{1: 'b', 2: 'A'}]


def _pdf(words):
    """A one-page PDF with each (x, y, text) written where it says. The font
    is set before the place, as Word writes it: pypdf then joins pieces on
    one line and loses where the later ones are."""
    ops = ''.join(f'BT /F1 10 Tf 1 0 0 1 {x} {y} Tm ({t}) Tj ET\n' for x, y, t in words)
    objects = ['<< /Type /Catalog /Pages 2 0 R >>',
               '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] '
               '/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>',
               f'<< /Length {len(ops)} >>\nstream\n{ops}endstream',
               '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    out, offsets = '%PDF-1.4\n', []
    for n, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f'{n} 0 obj\n{body}\nendobj\n'
    xref = len(out)
    out += f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n'
    out += ''.join(f'{o:010d} 00000 n \n' for o in offsets)
    out += f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'
    return out.encode('latin-1')


def _keyed_pdf():
    """The Hoá paper's key as LibreOffice prints it: "1a" is "1" over "a",
    and a narrow cell wraps, 1246 as "124" over "6", -0,7 as "-0," over "7"."""
    words = [(60, 700, 'Question 2. Prose that is not part of the key at all.'), (250, 650, 'Answer key')]
    words += [(80 + 26 * i, 620, str(i + 1)) for i in range(3)]
    words += [(80 + 26 * i, 606, v) for i, v in enumerate('BDC')]
    tf = [('1', 'a', 'D'), ('1', 'b', 'S'), ('2', 'a', 'S'), ('2', 'b', 'D')]
    for i, (n, letter, mark) in enumerate(tf):
        words += [(80 + 20 * i, 560, n), (80 + 20 * i, 546, letter), (80 + 20 * i, 525, mark)]
    for i, (first, rest) in enumerate([('124', '6'), ('-0,', '7')]):
        words += [(170 + 24 * i, 546, str(i + 1)), (168 + 24 * i, 525, first), (171 + 24 * i, 513, rest)]
    words += [(60, 470, 'Huong dan giai: the worked solutions follow')]
    return _pdf(words)


def test_a_pdfs_key_is_read_from_where_its_words_sit():
    from exercises.services.answer_key import key_from_pdf
    assert key_from_pdf(_keyed_pdf()) == [
        {1: 'B', 2: 'D', 3: 'C'},
        {1: {'a': True, 'b': False}, 2: {'a': False, 'b': True}},
        {1: '1246', 2: '-0,7'},
    ]


def test_a_pdf_without_a_key_heading_gives_no_key():
    from exercises.services.answer_key import key_from_pdf
    assert key_from_pdf(_pdf([(80, 620, '1'), (106, 620, '2'), (80, 606, 'B'), (106, 606, 'D')])) == []
    assert key_from_pdf(b'%PDF-1.7 not really') == []


def test_a_pdfs_key_is_the_papers_answer(client, reader, monkeypatch):
    monkeypatch.setattr('exercises.services.figures.cut', lambda data, mime, boxes: [[] for _ in boxes])
    reader({'found': True, 'questions': [
        {'label': 'Câu 2', 'part': 'PHẦN I', 'text': 'B?', 'answer': 'A'},
        {'label': 'Câu 2', 'part': 'PHẦN II', 'text': 'a) x. b) y.', 'answer': {'a': True, 'b': False}},
        {'label': 'Câu 1', 'part': 'PHẦN III', 'text': 'M?', 'answer': '124'},
    ]})
    res = _post(client, _keyed_pdf(), name='de.pdf', ctype='application/pdf')
    assert [q.get('answer') for q in res.json()['questions']] == ['D', {'a': False, 'b': True}, '1246']


def test_a_question_comes_back_in_its_shape(client, reader):
    """Options and statements apart from the stem, so the paper can be sat as
    printed; a shape that does not hold goes back into the text."""
    reader({'found': True, 'questions': [
        {'label': 'Câu 1', 'kind': 'choice', 'text': 'Chất nào là amine?',
         'options': [{'label': 'A.', 'text': 'Ethanol'}, {'label': 'b', 'text': 'Methylamine'}]},
        {'label': 'Câu 2', 'kind': 'true_false', 'text': 'Cho pin Zn – Cu.',
         'statements': [{'label': 'A', 'text': 'Zn bị oxi hoá.'}, {'label': 'b', 'text': 'Cu là cực âm.'}]},
        {'label': 'Câu 3', 'kind': 'short', 'text': 'Tính khối lượng.'},
        {'label': 'Câu 4', 'kind': 'choice', 'text': 'Chọn đáp án.', 'options': [{'label': 'A', 'text': 'Một'}]},
    ]})
    q = _post(client, JPEG).json()['questions']
    assert q[0]['kind'] == 'choice' and q[0]['options'] == [{'label': 'A', 'text': 'Ethanol'},
                                                           {'label': 'B', 'text': 'Methylamine'}]
    assert q[1]['kind'] == 'true_false' and [s['label'] for s in q[1]['statements']] == ['a', 'b']
    assert q[2]['kind'] == 'short'
    assert q[3]['kind'] == 'written' and q[3]['text'] == 'Chọn đáp án.\nA. Một'      # one option is no choice
