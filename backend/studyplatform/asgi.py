"""ASGI entrypoint: Django, with the Socket.IO server in front of it.

Django is served for every normal request; `socket.io` paths are handled by
the realtime server (notebooks/realtime.py), which shares this process, so
a broadcast from a REST view reaches the connected clients directly.

Run it with:  uvicorn studyplatform.asgi:application --port 8000 --reload
"""
import os

import django
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'studyplatform.settings')

# The apps must be loaded before notebooks.realtime imports models.
django.setup()

django_application = get_asgi_application()

import socketio  # noqa: E402 — after django.setup()

from notebooks.realtime import sio  # noqa: E402

application = socketio.ASGIApp(sio, other_asgi_app=django_application)
