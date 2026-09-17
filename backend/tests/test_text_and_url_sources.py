"""A source without a file: pasted text, or a fetched web page."""
import pytest

from notebooks.models import Source

pytestmark = pytest.mark.django_db

WORDS = ' '.join(f'word{i}' for i in range(40))


def _add_text(client, notebook, **body):
    return client.post(f'/api/notebooks/notebooks/{notebook.id}/add_text/', body, format='json')


def _add_url(client, notebook, **body):
    return client.post(f'/api/notebooks/notebooks/{notebook.id}/add_url/', body, format='json')


# ---- pasted text ------------------------------------------------------------------

def test_pasted_text_becomes_a_ready_source_at_once(client, notebook):
    res = _add_text(client, notebook, title='Cells', text='Plants absorb ﬁne carbon dioxide. ' + WORDS)

    assert res.status_code == 201, res.json()
    src = Source.objects.get(id=res.json()['id'])
    assert (src.file_type, src.status, src.title) == ('text', 'ready', 'Cells')
    assert not src.file
    assert src.extracted_text.startswith('Plants absorb fine carbon dioxide.')   # normalised


def test_a_missing_title_is_taken_from_the_first_line(client, notebook):
    res = _add_text(client, notebook, text='Chapter 3: Cells\n\n' + WORDS)
    assert res.json()['title'] == 'Chapter 3: Cells'


def test_text_too_short_to_generate_from_is_refused(client, notebook):
    res = _add_text(client, notebook, text='too short')
    assert res.status_code == 400
    assert 'short' in res.json()['detail'].lower()
    assert Source.objects.filter(file_type='text').count() == 0


def test_pasted_text_shows_in_the_notebooks_source_list(client, notebook):
    _add_text(client, notebook, title='Pasted notes', text=WORDS)
    body = client.get(f'/api/notebooks/notebooks/{notebook.id}/').json()
    kinds = {s['title']: s['file_type'] for s in body['sources']}
    assert kinds['Pasted notes'] == 'text'


# ---- a link ----------------------------------------------------------------------

class _Resp:
    def __init__(self, text, status=200, ctype='text/html; charset=utf-8'):
        self.text, self.status_code = text, status
        self.headers = {'Content-Type': ctype}
        self.content = text.encode()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr('notebooks.services.web_source._resolve', lambda host: ['93.184.216.34'])


def test_a_page_becomes_a_source_titled_from_the_page(client, notebook, monkeypatch, public_dns):
    html = f'<html><head><title>Photosynthesis</title></head><body><p>{WORDS}</p></body></html>'
    calls = []
    monkeypatch.setattr('notebooks.services.fetch_page.requests.get',
                        lambda url, **kw: calls.append((url, kw)) or _Resp(html))

    res = _add_url(client, notebook, url='https://example.com/photo')

    assert res.status_code == 201, res.json()
    src = Source.objects.get(id=res.json()['id'])
    assert (src.file_type, src.status, src.title, src.original_filename) == \
        ('url', 'ready', 'Photosynthesis', 'https://example.com/photo')
    assert 'word0' in src.extracted_text
    assert calls[0][1]['timeout'] == 10 and calls[0][1]['stream'] is True


def test_a_private_link_is_refused_without_touching_the_network(client, notebook, monkeypatch):
    monkeypatch.setattr('notebooks.services.web_source._resolve', lambda host: ['10.0.0.1'])
    def boom(*a, **k):
        raise AssertionError('must not fetch')
    monkeypatch.setattr('notebooks.services.fetch_page.requests.get', boom)

    res = _add_url(client, notebook, url='http://intranet.corp/secrets')

    assert res.status_code == 400
    assert 'private' in res.json()['detail'].lower()


def test_a_page_with_no_text_is_refused(client, notebook, monkeypatch, public_dns):
    monkeypatch.setattr('notebooks.services.fetch_page.requests.get',
                        lambda url, **kw: _Resp('<html><body><script>x()</script></body></html>'))
    res = _add_url(client, notebook, url='https://example.com/empty')
    assert res.status_code == 400
    assert Source.objects.filter(file_type='url').count() == 0


def test_a_network_failure_is_a_400_with_a_reason(client, notebook, monkeypatch, public_dns):
    import requests
    def timeout(*a, **k):
        raise requests.Timeout('slow')
    monkeypatch.setattr('notebooks.services.fetch_page.requests.get', timeout)
    res = _add_url(client, notebook, url='https://example.com/slow')
    assert res.status_code == 400
    assert 'fetch' in res.json()['detail'].lower() or 'reach' in res.json()['detail'].lower()


def test_a_non_html_non_pdf_response_is_refused(client, notebook, monkeypatch, public_dns):
    monkeypatch.setattr('notebooks.services.fetch_page.requests.get',
                        lambda url, **kw: _Resp('PK\x03\x04...', ctype='application/zip'))
    res = _add_url(client, notebook, url='https://example.com/archive.zip')
    assert res.status_code == 400
    assert 'page' in res.json()['detail'].lower()


def test_another_users_notebook_is_not_found(client, other_user):
    from notebooks.models import Notebook
    theirs = Notebook.objects.create(user=other_user, title='Theirs')
    assert _add_text(client, theirs, text=WORDS).status_code == 404


# ---- links that are PDFs, and sites that block automated access ------------------

def test_a_site_that_blocks_automated_access_says_so(client, notebook, monkeypatch, public_dns):
    # ACM, Elsevier and the like sit behind a bot challenge: HTTP 403 with
    # a Cloudflare page. The student can still download the file themselves.
    monkeypatch.setattr('notebooks.services.fetch_page.requests.get',
                        lambda url, **kw: _Resp('<html>Just a moment…</html>', status=403))
    res = _add_url(client, notebook, url='https://dl.acm.org/doi/pdf/10.1145/1629607.1629613')
    assert res.status_code == 400
    detail = res.json()['detail'].lower()
    assert 'block' in detail and 'upload' in detail


def test_a_pdf_link_becomes_a_pdf_source(client, notebook, monkeypatch, public_dns):
    pdf_bytes = b'%PDF-1.4 fake'
    class PdfResp(_Resp):
        def __init__(self):
            super().__init__('', ctype='application/pdf'); self.content = pdf_bytes
    monkeypatch.setattr('notebooks.services.fetch_page.requests.get', lambda url, **kw: PdfResp())
    monkeypatch.setattr('notebooks.views.extract_text_from_document',
                        lambda path, kind: ('Extracted paper text. ' + WORDS, 7))

    res = _add_url(client, notebook, url='https://arxiv.org/pdf/1234.5678v1.pdf', title='Paper')

    assert res.status_code == 201, res.json()
    src = Source.objects.get(id=res.json()['id'])
    assert (src.file_type, src.status, src.page_count, src.original_filename) == \
        ('pdf', 'ready', 7, 'https://arxiv.org/pdf/1234.5678v1.pdf')
    assert src.file and src.file.read() == pdf_bytes
    assert src.extracted_text.startswith('Extracted paper text.')


def test_a_pdf_link_that_yields_no_text_is_refused(client, notebook, monkeypatch, public_dns):
    class PdfResp(_Resp):
        def __init__(self):
            super().__init__('', ctype='application/pdf'); self.content = b'%PDF-1.4 scanned'
    monkeypatch.setattr('notebooks.services.fetch_page.requests.get', lambda url, **kw: PdfResp())
    monkeypatch.setattr('notebooks.views.extract_text_from_document', lambda path, kind: ('', 3))
    res = _add_url(client, notebook, url='https://arxiv.org/pdf/scan.pdf')
    assert res.status_code == 400
    assert Source.objects.filter(file_type='pdf', original_filename__startswith='https').count() == 0
