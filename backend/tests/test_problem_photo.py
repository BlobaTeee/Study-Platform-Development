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
    assert res.json()['questions'] == [{'label': 'Câu 1', 'instruction': '', 'text': r'Tính $\int_0^1 x^2\,dx$.', 'figures': []}]
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


def test_a_question_without_a_label_is_numbered(client, reader):
    reader({'found': True, 'questions': [{'text': 'Solve $x + 1 = 3$.'}, {'label': '  ', 'text': 'Find $x$.'}]})
    assert [q['label'] for q in _post(client, JPEG).json()['questions']] == ['1', '2']


def test_a_reply_with_one_text_still_works(client, reader):
    reader({'found': True, 'text': 'Solve $x + 1 = 3$ for $x$.'})
    assert _post(client, JPEG).json()['questions'] == [{'label': '1', 'instruction': '', 'text': 'Solve $x + 1 = 3$ for $x$.', 'figures': []}]


def test_the_reader_is_told_what_not_to_copy(client, reader):
    r = reader(_one('Solve x + 1 = 3 for x.'))
    _post(client, JPEG)
    prompt = r.prompt.lower()
    assert 'handwrit' in prompt                    # a circled answer would give the answer away
    assert 'variation table' in prompt and 'arrow' in prompt
    assert 'exactly as printed' in prompt          # n_2 stays n_2
    assert 'restart' in prompt                     # Part II's question 1 is not Part I's
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
