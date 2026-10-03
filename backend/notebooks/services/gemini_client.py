import json
import re
import time
from django.conf import settings


class GeminiNotConfiguredError(Exception):
    pass


class GeminiGenerationError(Exception):
    pass


class GeminiQuotaError(GeminiGenerationError):
    pass


def is_quota_error(exc: BaseException) -> bool:
    msg = str(exc).upper()
    return (
        '429' in msg
        or 'RESOURCE_EXHAUSTED' in msg
        or 'QUOTA' in msg
        or 'RATE_LIMIT' in msg
    )


def is_missing_model_error(exc: BaseException) -> bool:
    """The model id is gone. Google retires ids and answers 404; the point of
    the fallback list is to carry on with the next one."""
    msg = str(exc).upper()
    return '404' in msg or 'NOT_FOUND' in msg or 'NOT FOUND' in msg


def is_transient_error(exc: BaseException) -> bool:
    """A server-side hiccup rather than something wrong with the request.

    Gemini answers 503 UNAVAILABLE when a model is busy and 500 INTERNAL when
    something failed on its side; both are worth retrying on the next model
    in the list rather than failing a student's generation outright.
    """
    msg = str(exc).upper()
    return (
        '503' in msg
        or 'UNAVAILABLE' in msg
        or 'OVERLOADED' in msg
        or '500 INTERNAL' in msg
        or 'INTERNAL ERROR' in msg
        or '504' in msg
        or 'DEADLINE_EXCEEDED' in msg
        # A deadline of our own making: the model never answered in time.
        or 'TIMEOUT' in msg
        or 'TIMED OUT' in msg
    )


def quota_user_message() -> str:
    return (
        'Gemini API quota exceeded (free tier limit). '
        'Wait about a minute and try again, switch GEMINI_MODEL in backend/.env '
        '(e.g. gemini-3.1-flash-lite), or enable billing at https://aistudio.google.com. '
        'Basic local flashcards/quiz can be used if USE_LOCAL_FALLBACK_ON_QUOTA=True.'
    )


# The server's own floor: "Minimum allowed deadline is 10s".
MIN_TIMEOUT_SECONDS = 10


def _genai_client_class():
    try:
        from google import genai
    except ImportError as exc:
        raise GeminiNotConfiguredError('Install google-genai: pip install google-genai') from exc
    return genai.Client


def _get_client():
    api_key = getattr(settings, 'GEMINI_API_KEY', '') or ''
    if not api_key:
        raise GeminiNotConfiguredError(
            'GEMINI_API_KEY is not set. Add it to backend/.env'
        )
    from google.genai import types
    # Without a deadline, a model under heavy demand does not fail — it hangs,
    # and so does the student waiting for their quiz. Measuring 3.8-flash on a
    # busy afternoon sat for over half an hour without an answer or an error.
    # Timing out turns that into a transient error, which hands the work to the
    # next model in the list within seconds.
    # Gemini refuses a deadline under ten seconds with a 400, which is not a
    # transient error — so too small a setting would kill generation outright
    # rather than merely hurrying it.
    seconds = max(MIN_TIMEOUT_SECONDS, int(getattr(settings, 'GEMINI_TIMEOUT_SECONDS', 30)))
    return _genai_client_class()(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=seconds * 1000),
    )


def _model_list() -> list[str]:
    primary = getattr(settings, 'GEMINI_MODEL', 'gemini-3.8-flash')
    fallbacks = getattr(settings, 'GEMINI_MODEL_FALLBACKS', '')
    extra = [m.strip() for m in fallbacks.split(',') if m.strip()]
    seen = set()
    models = []
    for name in [primary, *extra]:
        if name and name not in seen:
            seen.add(name)
            models.append(name)
    return models


def _parse_json_response(text: str) -> dict:
    cleaned = (text or '').strip()
    if cleaned.startswith('```'):
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise GeminiGenerationError('Model returned invalid JSON.') from exc


def _is_thinking_rejected(exc) -> bool:
    """A model refusing the thinking setting, not a model that is broken.

    gemini-2.5-flash answers 400 INVALID_ARGUMENT to `thinking_level`, which
    belongs to the 3.x family. The model itself is fine, so the call is worth
    repeating without that one setting.
    """
    text = str(exc).lower()
    return '400' in text and 'thinking' in text


def _request_config(thinking: str | None = None):
    """Ask for JSON outright, and say how much the model should think.

    JSON is requested through the API rather than only in the prompt, so a
    chatty model cannot wrap the answer in prose and break parsing. The
    thinking setting matters for cost: measured on one excerpt, the thinking
    part was 2.089 tokens against 765 of actual answer on gemini-2.5-flash —
    more than half the spend, on text nobody reads.
    """
    from google.genai import types
    mode = (thinking if thinking is not None
            else getattr(settings, 'GEMINI_THINKING', 'default')).lower()
    thinking_config = None
    if mode == 'off':
        thinking_config = types.ThinkingConfig(thinking_budget=0)
    elif mode in ('low', 'high'):
        thinking_config = types.ThinkingConfig(thinking_level=mode)
    return types.GenerateContentConfig(
        response_mime_type='application/json',
        thinking_config=thinking_config,
    )


def generate_json(prompt: str) -> dict:
    client = _get_client()
    models = _model_list()
    last_quota_error = None
    last_transient_error = None

    for model in models:
        try:
            try:
                response = client.models.generate_content(
                    model=model, contents=prompt, config=_request_config())
            except Exception as exc:
                if not _is_thinking_rejected(exc):
                    raise
                # This model is older than the setting; ask it again plainly.
                response = client.models.generate_content(
                    model=model, contents=prompt, config=_request_config('default'))
            return _parse_json_response(response.text or '')
        except (GeminiNotConfiguredError, GeminiGenerationError):
            raise
        except Exception as exc:
            if is_quota_error(exc):
                last_quota_error = exc
                time.sleep(1)
                continue
            if is_transient_error(exc) or is_missing_model_error(exc):
                # Busy or retired: the next one in the list usually works.
                last_transient_error = exc
                continue
            raise GeminiGenerationError(str(exc)) from exc

    # Quota is the more actionable of the two, so it wins the report.
    if last_quota_error:
        raise GeminiQuotaError(quota_user_message()) from last_quota_error
    if last_transient_error:
        raise GeminiGenerationError(
            f'Every Gemini model was busy: {last_transient_error}') from last_transient_error
    raise GeminiGenerationError('No Gemini model available.')
