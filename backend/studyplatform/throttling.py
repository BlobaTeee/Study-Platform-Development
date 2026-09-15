"""Rate limits for the endpoints that cost something to serve.

Generation is the only expensive thing this API does: each call goes to
Gemini (metered), Ollama (minutes of CPU on a laptop), or spaCy. Every other
endpoint is a database read, so it only gets the blanket per-user limit set
in settings. Counters live in Django's cache — the default locmem cache is
per-process, so a multi-worker deployment needs a shared one (Redis, memcached)
or each worker will grant the full allowance on its own.
"""
from rest_framework.throttling import UserRateThrottle


class GenerationRateThrottle(UserRateThrottle):
    """Per-user allowance for anything that generates study content.

    Rate is `REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['generate']`. Applied per
    action rather than per viewset so listing or deleting cards in the same
    viewset is never slowed by someone else's generation spree.
    """
    scope = 'generate'
