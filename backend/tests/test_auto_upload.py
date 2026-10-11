"""Tải tài liệu lên trang Sổ tay: AI tự xếp vào sổ tay đúng môn.

A file dropped on the notebooks page joins the student's own notebook for
its subject, or starts a new one named for the subject. Naming rides on the
summary request that every upload already makes, so placing a file costs
no extra AI request. It is never placed in a notebook someone else shared:
that would hand the document to people it was not meant for.
"""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from notebooks.models import Notebook, Source
from tests.conftest import make_source

pytestmark = pytest.mark.django_db

URL = '/api/notebooks/notebooks/auto_upload/'

CHEM = """Atoms are made of protons, neutrons and electrons. The periodic table orders the elements by
atomic number, and electrons fill shells around the nucleus. Covalent bonds form when atoms share electron
pairs; ionic bonds form when electrons transfer from a metal to a non-metal, giving ions held together by
electrostatic attraction. Molecules such as water are polar because oxygen pulls the shared electrons
towards itself. Chemical bonds store energy, and breaking bonds in a reaction absorbs energy.""" * 3
CHEM_NEW = """Chemical bonding, part two. Covalent bonds share electron pairs between atoms, and the
shared electrons sit between the two nuclei. Ionic bonds form when electrons transfer from a metal atom to a
non-metal atom, so the ions are held by electrostatic attraction. Polar molecules such as water have shared
electrons pulled towards the more electronegative atom. Breaking chemical bonds absorbs energy and forming
bonds releases energy, which decides whether a reaction gives out heat.""" * 3
HISTORY = """The treaty ended the war in 1648 and redrew the borders of the empire. Envoys negotiated for
years over territory, religion and the rights of the princes, and the settlement shaped European diplomacy
for a century. Historians still debate whether it created the modern idea of state sovereignty or simply
recorded a balance of power that the fighting had already produced.""" * 3


class _Namer:
    """Answers the upload's one request: a summary and the subject's name."""
    name = 'stub'

    def __init__(self, subject='Lịch sử châu Âu'):
        self.subject = subject
        self.calls = 0

    def generate_json(self, prompt):
        self.calls += 1
        return {'summary': 'A short overview.', 'subject': self.subject}

    def summarize(self, text, title=''):
        self.calls += 1
        return 'A short overview.'


@pytest.fixture
def namer(monkeypatch):
    n = _Namer()
    for target in ('notebooks.services.ingest.get_ai_provider',
                   'notebooks.services.key_points.get_ai_provider'):
        monkeypatch.setattr(target, lambda: n, raising=False)
    return n


@pytest.fixture
def text_of(monkeypatch):
    """Uploads carry their text in the file body; extraction is not under test."""
    def extract(path, file_type):
        with open(path, encoding='utf-8') as fh:
            return fh.read(), 1
    monkeypatch.setattr('notebooks.services.ingest.extract_text_from_document', extract)
    monkeypatch.setattr('notebooks.services.auto_place.extract_text_from_document', extract, raising=False)


def _upload(client, text, name='lecture.pdf'):
    f = SimpleUploadedFile(name, text.encode('utf-8'), content_type='application/pdf')
    return client.post(URL, {'file': f}, format='multipart')


@pytest.fixture
def chemistry(user):
    nb = Notebook.objects.create(user=user, title='Hoá học')
    make_source(nb, 'Liên kết hoá học', CHEM)
    return nb


def test_a_file_joins_the_notebook_of_its_subject(client, chemistry, namer, text_of):
    res = _upload(client, CHEM_NEW)

    assert res.status_code == 201, res.json()
    body = res.json()
    assert body['notebook']['id'] == chemistry.id
    assert body['created_notebook'] is False
    assert Source.objects.get(id=body['source']['id']).notebook_id == chemistry.id


def test_a_new_subject_starts_a_notebook_named_for_it(client, user, chemistry, namer, text_of):
    res = _upload(client, HISTORY)

    body = res.json()
    assert res.status_code == 201, body
    assert body['created_notebook'] is True
    assert body['notebook']['title'] == 'Lịch sử châu Âu'
    assert Notebook.objects.get(id=body['notebook']['id']).user == user


def test_placing_a_file_costs_no_extra_request(client, chemistry, namer, text_of):
    _upload(client, HISTORY)      # new notebook: summary and name in one request
    _upload(client, CHEM_NEW)     # existing notebook: the summary only

    assert namer.calls == 2


def test_files_of_one_new_subject_land_together(client, chemistry, namer, text_of):
    first = _upload(client, HISTORY).json()
    second = _upload(client, HISTORY.replace('1648', '1649'), name='week2.pdf').json()

    assert second['notebook']['id'] == first['notebook']['id']
    assert second['created_notebook'] is False


def test_a_named_subject_that_already_has_a_notebook_uses_it(client, user, namer, text_of):
    # The text matches nothing yet, but the model names a subject the student
    # already has a notebook for: one notebook, not two with the same name.
    existing = Notebook.objects.create(user=user, title='lịch sử châu âu')

    body = _upload(client, HISTORY).json()

    assert body['notebook']['id'] == existing.id


def test_a_shared_notebook_never_receives_the_file(client, user, other_user, namer, text_of):
    theirs = Notebook.objects.create(user=other_user, title='Hoá học')
    make_source(theirs, 'Their lecture', CHEM)
    from notebooks.models import NotebookMember
    NotebookMember.objects.get_or_create(notebook=theirs, user=user, defaults={'role': 'member'})

    body = _upload(client, CHEM_NEW).json()

    assert body['notebook']['id'] != theirs.id
    assert Notebook.objects.get(id=body['notebook']['id']).user == user


def test_without_a_provider_a_new_notebook_is_named_from_the_file(client, monkeypatch, text_of):
    from tests.conftest import _NoProvider
    for target in ('notebooks.services.ingest.get_ai_provider',
                   'notebooks.services.key_points.get_ai_provider'):
        monkeypatch.setattr(target, lambda: _NoProvider(), raising=False)

    body = _upload(client, HISTORY, name='Westphalia_treaty.pdf').json()

    assert body['created_notebook'] is True
    assert body['notebook']['title'] == 'Westphalia treaty'


def test_an_unsupported_file_is_refused(client, namer, text_of):
    f = SimpleUploadedFile('notes.exe', b'x', content_type='application/octet-stream')
    assert client.post(URL, {'file': f}, format='multipart').status_code == 400


# ---- moving it afterwards ------------------------------------------------------

def test_a_misplaced_file_can_be_moved_to_another_of_my_notebooks(client, user, chemistry, namer, text_of):
    body = _upload(client, HISTORY).json()
    source_id, auto_nb = body['source']['id'], body['notebook']['id']

    res = client.post(f'/api/notebooks/sources/{source_id}/move/',
                      {'notebook_id': chemistry.id, 'drop_empty_notebook': True}, format='json')

    assert res.status_code == 200, res.json()
    assert Source.objects.get(id=source_id).notebook_id == chemistry.id
    # The notebook made for it a moment ago is left empty and removed.
    assert not Notebook.objects.filter(id=auto_nb).exists()


def test_a_notebook_the_student_made_is_kept_even_when_emptied(client, user, chemistry, namer, text_of):
    mine = Notebook.objects.create(user=user, title='Mine')
    source = make_source(mine, 'Only file', HISTORY)

    client.post(f'/api/notebooks/sources/{source.id}/move/', {'notebook_id': chemistry.id}, format='json')

    assert Notebook.objects.filter(id=mine.id).exists()


def test_a_file_can_be_moved_into_a_new_notebook(client, user, chemistry, namer, text_of):
    source = make_source(chemistry, 'Treaty', HISTORY)

    res = client.post(f'/api/notebooks/sources/{source.id}/move/', {'new_notebook_title': 'Lịch sử'}, format='json')

    assert res.status_code == 200, res.json()
    moved_to = Source.objects.get(id=source.id).notebook
    assert moved_to.title == 'Lịch sử' and moved_to.user == user


def test_a_file_cannot_be_moved_into_someone_elses_notebook(client, other_user, chemistry, namer, text_of):
    body = _upload(client, CHEM_NEW).json()
    theirs = Notebook.objects.create(user=other_user, title='Theirs')

    res = client.post(f"/api/notebooks/sources/{body['source']['id']}/move/", {'notebook_id': theirs.id}, format='json')

    assert res.status_code in (400, 404)
    assert Source.objects.get(id=body['source']['id']).notebook_id == chemistry.id


def test_the_notebook_list_says_which_notebooks_are_mine(client, user, other_user, chemistry):
    # The move menu offers only these.
    theirs = Notebook.objects.create(user=other_user, title='Theirs')
    from notebooks.models import NotebookMember
    NotebookMember.objects.get_or_create(notebook=theirs, user=user, defaults={'role': 'member'})

    listed = client.get('/api/notebooks/notebooks/').json()
    listed = listed.get('results', listed) if isinstance(listed, dict) else listed
    owned = {nb['id']: nb['is_owner'] for nb in listed}

    assert owned[chemistry.id] is True
    assert owned[theirs.id] is False
