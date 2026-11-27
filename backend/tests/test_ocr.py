"""A scanned PDF (page pictures, no text) is read by OCR in the background.

On 2026-11-24 a 373-page scanned review book could not be added at all: it
was over the 10 MB limit, and pypdf found no text in it. Tesseract reads the
pages on this machine (no AI request), which takes minutes, so the document
shows as processing and the page checks back until it is ready.
"""
import io
import os
import shutil

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from notebooks.models import Notebook, Source
from notebooks.services import ocr

REAL_AVAILABLE = ocr.available
# PIL's own font has no Vietnamese letters: a page drawn with it is boxes.
VIETNAMESE_FONT = next((f for f in ('/System/Library/Fonts/Supplemental/Arial.ttf',
                                    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf') if os.path.exists(f)), None)          # before conftest stands it in for every test
pytestmark = pytest.mark.django_db


def _scanned_pdf(lines=('Câu 1: Vai trò của vật chất di truyền là gì?',), pages=1):
    """A PDF whose pages are only pictures, as a scanner makes them."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(VIETNAMESE_FONT, 36) if VIETNAMESE_FONT else ImageFont.load_default(size=36)
    pictures = []
    for _ in range(pages):
        page = Image.new('RGB', (1240, 1754), 'white')
        draw = ImageDraw.Draw(page)
        for n, line in enumerate(lines):
            draw.text((80, 120 + 60 * n), line, fill='black', font=font)
        pictures.append(page)
    out = io.BytesIO()
    pictures[0].save(out, format='PDF', save_all=True, append_images=pictures[1:])
    return out.getvalue()


def _upload(client, url, data, name='sach.pdf'):
    return client.post(url, {'file': SimpleUploadedFile(name, data, content_type='application/pdf')},
                       format='multipart')


@pytest.fixture
def ocr_reads(monkeypatch):
    """OCR there, reading every scanned PDF as `text`, and the background run
    done in line so the test sees its end."""
    from notebooks.services import ingest

    def use(text):
        monkeypatch.setattr(ocr, 'available', lambda: True)
        monkeypatch.setattr(ocr, 'read_pdf', lambda path, first_pages=None: text)
        ran = []
        monkeypatch.setattr(ingest, 'process_in_background',
                            lambda source: (ran.append((source.id, source.status)), ingest.process_source(source)))
        return ran
    return use


def test_a_pdf_with_text_is_not_scanned():
    assert not ocr.is_scanned('word ' * 200, 2)
    assert ocr.is_scanned('', 373)
    assert ocr.is_scanned('12', 3)             # a page number or two is not text
    assert not ocr.is_scanned('', 0)


def test_a_scanned_pdf_is_read_in_the_background(client, notebook, ocr_reads):
    ran = ocr_reads('Vật chất di truyền lưu trữ và truyền đạt thông tin di truyền. ' * 40)
    res = _upload(client, f'/api/notebooks/notebooks/{notebook.id}/upload_pdf/', _scanned_pdf())
    assert res.status_code == 201
    source = Source.objects.get(id=res.json()['id'])
    assert ran == [(source.id, 'processing')]          # handed to the background unread
    assert source.status == 'ready' and 'vật chất di truyền' in source.extracted_text.lower()


def test_without_tesseract_a_scanned_pdf_fails_as_before(client, notebook, monkeypatch):
    monkeypatch.setattr(ocr, 'available', lambda: False)
    res = _upload(client, f'/api/notebooks/notebooks/{notebook.id}/upload_pdf/', _scanned_pdf())
    source = Source.objects.get(id=res.json()['id'])
    assert source.status == 'failed' and 'scanned' in source.error_message


def test_a_scanned_upload_is_placed_by_its_first_pages(client, user, ocr_reads):
    ran = ocr_reads('Sinh học di truyền: gene, DNA và đột biến. ' * 40)
    res = _upload(client, '/api/notebooks/notebooks/auto_upload/', _scanned_pdf(), name='Biology Review.pdf')
    assert res.status_code == 201
    body = res.json()
    source = Source.objects.get(id=body['source']['id'])
    assert ran == [(source.id, 'processing')] and source.status == 'ready'
    assert Notebook.objects.get(id=body['notebook']['id']).title == 'Biology Review'


@pytest.mark.skipif(not shutil.which('tesseract') or not VIETNAMESE_FONT,
                    reason='Tesseract, or a font with Vietnamese letters, is not installed here')
def test_tesseract_reads_vietnamese_off_a_page_picture(tmp_path):
    REAL_AVAILABLE.cache_clear()
    if not REAL_AVAILABLE():
        pytest.skip('Tesseract has no Vietnamese here')
    path = tmp_path / 'scan.pdf'
    path.write_bytes(_scanned_pdf(['Câu 1: Vai trò của vật chất di truyền là gì?',
                                   'D. Lưu trữ và truyền đạt thông tin di truyền.'], pages=2))
    text = ocr.read_pdf(str(path))
    assert 'vật chất di truyền' in text.lower()
    assert text.lower().count('truyền đạt') == 2            # both pages, in order
    assert ocr.read_pdf(str(path), first_pages=1).lower().count('truyền đạt') == 1


def test_a_read_cut_off_by_a_restart_does_not_stay_processing(client, notebook):
    """A server restart ends the background read; the document then says so
    instead of showing as processing for ever."""
    from datetime import timedelta
    from django.utils import timezone
    stuck = Source.objects.create(notebook=notebook, title='Sách', file_type='pdf', status='processing')
    going = Source.objects.create(notebook=notebook, title='Sách 2', file_type='pdf', status='processing')
    Source.objects.filter(id=stuck.id).update(updated_at=timezone.now() - timedelta(minutes=45))

    client.get(f'/api/notebooks/notebooks/{notebook.id}/')

    stuck.refresh_from_db(), going.refresh_from_db()
    assert (stuck.status, going.status) == ('failed', 'processing')
    assert 'upload it again' in stuck.error_message


def test_a_documents_error_is_shown_in_the_readers_language(client, notebook, settings):
    from notebooks.services.ingest import EMPTY_TEXT_MESSAGES
    source = Source.objects.create(notebook=notebook, title='Scan', file_type='pdf', status='failed',
                                   error_message=EMPTY_TEXT_MESSAGES['pdf'])
    res = client.get(f'/api/notebooks/sources/{source.id}/', HTTP_ACCEPT_LANGUAGE='vi')
    assert res.json()['error_message'] == 'Không trích được chữ. PDF có thể chỉ toàn ảnh scan.'
