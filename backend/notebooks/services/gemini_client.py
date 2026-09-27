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
    )


def quota_user_message() -> str:
    return (
        'Gemini API quota exceeded (free tier limit). '
        'Wait about a minute and try again, switch GEMINI_MODEL in backend/.env '
        '(e.g. gemini-3.1-flash-lite), or enable billing at https://aistudio.google.com. '
        'Basic local flashcards/quiz can be used if USE_LOCAL_FALLBACK_ON_QUOTA=True.'
    )


def _get_client():
    api_key = getattr(settings, 'GEMINI_API_KEY', '') or ''
    if not api_key:
        raise GeminiNotConfiguredError(
            'GEMINI_API_KEY is not set. Add it to backend/.env'
        )
    try:
        from google import genai
    except ImportError as exc:
        raise GeminiNotConfiguredError('Install google-genai: pip install google-genai') from exc
    return genai.Client(api_key=api_key)


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


def generate_json(prompt: str) -> dict:
    client = _get_client()
    models = _model_list()
    last_quota_error = None
    last_transient_error = None

    for model in models:
        try:
            response = client.models.generate_content(model=model, contents=prompt)
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
