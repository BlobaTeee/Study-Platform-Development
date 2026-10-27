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
    assert res.json()['questions'] == [{'label': 'Câu 1', 'instruction': '', 'text': r'Tính $\int_0^1 x^2\,dx$.'}]
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
    assert _post(client, JPEG).json()['questions'] == [{'label': '1', 'instruction': '', 'text': 'Solve $x + 1 = 3$ for $x$.'}]


def test_the_reader_is_told_what_not_to_copy(client, reader):
    r = reader(_one('Solve x + 1 = 3 for x.'))
    _post(client, JPEG)
    prompt = r.prompt.lower()
    assert 'handwrit' in prompt                    # a circled answer would give the answer away
    assert 'variation table' in prompt and 'arrow' in prompt
    assert 'exactly as printed' in prompt          # n_2 stays n_2
    assert 'restart' in prompt                     # Part II's question 1 is not Part I's


def test_the_type_is_read_from_the_bytes_not_the_name(client, reader):
    r = reader(_one('Solve x + 1 = 3 for x.'))
    _post(client, PNG, name='photo.jpg', ctype='image/jpeg')
    assert r.images[0][1] == 'image/png'


def test_a_photo_without_a_problem_says_so(client, reader):
    reader({'found': False, 'questions': []})
    res = _post(client, JPEG)
    assert res.status_code == 400 and res.json()['no_problem'] is True


def test_something_that_is_not_an_image_is_refused_without_a_request(client, reader):
    r = reader({'found': True, 'text': 'x'})
    res = _post(client, b'%PDF-1.7 not a picture', name='notes.pdf', ctype='application/pdf')
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
