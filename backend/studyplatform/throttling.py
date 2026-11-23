"""Rate limits for the endpoints that cost something to serve.

Generation is the only expensive thing this API does: each call goes to
Gemini (metered), Ollama (minutes of CPU on a laptop), or spaCy. Every other
endpoint is a database read, so it only gets the blanket per-user limit set
in settings. Counters live in Django's cache — the default locmem cache is
per-process, so a multi-worker deployment needs a shared one (Redis, memcached)
or each worker will grant the full allowance on its own.

A request that fails on the server's side (the AI overloaded, a timeout:
any 5xx) is given back: it cost nothing, and a student retrying through an
overload would otherwise run out of allowance without getting anything.
"""
from math import ceil

from asgiref.sync import iscoroutinefunction

from django.core.cache import cache
from django.utils.decorators import sync_and_async_middleware
from django.utils.translation import gettext as _
from rest_framework.exceptions import Throttled
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import exception_handler as drf_exception_handler


class GenerationRateThrottle(UserRateThrottle):
    """Per-user allowance for anything that generates study content.

    Rate is `REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['generate']`. Applied per
    action rather than per viewset so listing or deleting cards in the same
    viewset is never slowed by someone else's generation spree.
    """
    scope = 'generate'

    def allow_request(self, request, view):
        allowed = super().allow_request(request, view)
        if allowed and getattr(self, "key", None):      # no key when the limit is off
            # On the Django request, which the middleware below sees.
            django_request = getattr(request, '_request', request)
            django_request._generation_charge = (self.key, self.now, self.duration)
        return allowed


def refund(key: str, stamp: float, duration: int) -> None:
    history = cache.get(key, [])
    if stamp in history:
        history.remove(stamp)
        cache.set(key, history, duration)


@sync_and_async_middleware
def RefundFailedGeneration(get_response):
    """Gives back the allowance a generation request spent when it failed
    on the server's side. Async-capable: a sync-only middleware would make
    the ASGI server run every request one at a time."""
    def settle(request, response):
        charge = getattr(request, '_generation_charge', None)
        if charge and response.status_code >= 500:
            refund(*charge)
        return response

    if iscoroutinefunction(get_response):
        async def middleware(request):
            return settle(request, await get_response(request))
    else:
        def middleware(request):
            return settle(request, get_response(request))
    return middleware


def exception_handler(exc, context):
    """DRF's handler, with the throttle's message in the student's language
    and in minutes ("Expected available in 2961 seconds" says little)."""
    response = drf_exception_handler(exc, context)
    if isinstance(exc, Throttled) and response is not None:
        minutes = max(1, ceil((exc.wait or 60) / 60))
        response.data = {'detail': _("You've used this hour's AI requests. Try again in %(minutes)s min.")
                         % {'minutes': minutes}}
    return response
