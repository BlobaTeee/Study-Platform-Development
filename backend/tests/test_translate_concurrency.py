"""Translating must not hold up the rest of the API.

Under ASGI (uvicorn), Django runs every synchronous view on one shared
thread, one request at a time. A translation takes seconds (longer when the
model loads), so while a page waited for one, everything else queued
behind it: generating flashcards or a quiz seemed to take forever.
"""
import asyncio
import threading
import time

import pytest
from django.test import AsyncClient

pytestmark = pytest.mark.django_db(transaction=True)
URL = '/api/notebooks/translate/'
SLOW = 1.5


@pytest.fixture
def signed_in(user, monkeypatch):
    monkeypatch.setattr('users.authentication.SupabaseJWTAuthentication.authenticate',
                        lambda self, request: (user, None))


@pytest.fixture
def slow_machine(monkeypatch):
    started = threading.Event()

    def translate(texts, source, target):
        started.set()
        time.sleep(SLOW)
        return [f'[{source}>{target}] {t}' for t in texts]
    monkeypatch.setattr('notebooks.services.translate.machine_translate', translate)
    return started


def test_other_requests_are_answered_while_a_translation_runs(signed_in, slow_machine):
    async def run():
        client = AsyncClient(HTTP_HOST='localhost')
        slow = asyncio.create_task(client.post(
            URL, {'texts': ['Energy is conserved in every phase change.'], 'to': 'vi'},
            content_type='application/json'))
        while not slow_machine.is_set():
            await asyncio.sleep(0.01)
        t0 = time.monotonic()
        other = await client.get('/api/notebooks/')
        waited = time.monotonic() - t0
        translated = await slow
        return other.status_code, waited, translated

    status, waited, translated = asyncio.run(run())
    assert status == 200
    assert translated.status_code == 200
    assert translated.json()['translations'] == ['[en>vi] Energy is conserved in every phase change.']
    assert waited < SLOW / 2, f'the other request waited {waited:.2f}s behind the translation'
