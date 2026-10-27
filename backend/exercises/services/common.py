"""What the problem writer and the grader share: the error vocabulary, the
model call with failures a student can act on, and the language to write in."""
import logging

from django.utils.translation import gettext as _

from ml_pipeline.language import detect_language
from notebooks.services import ai_provider
from notebooks.services.gemini_client import GeminiNotConfiguredError, GeminiQuotaError, is_quota_error

logger = logging.getLogger(__name__)

# One vocabulary for every subject, so Progress can compare a law notebook
# with a chemistry one. The detail sentence carries what is subject-specific.
ERROR_TYPES = ('misread', 'concept', 'missing_step', 'execution', 'unsupported')
ERROR_MEANINGS = {
    'misread': 'misread the problem: answered a different question, missed a given or a condition',
    'concept': 'wrong concept or principle: applied a rule, definition or idea that does not hold here',
    'missing_step': 'missing step or reasoning: skipped something the answer needs, or stopped short',
    'execution': 'slip carrying out a step: arithmetic, units, syntax, a wrong word or value',
    'unsupported': 'conclusion without grounds: claims something the steps do not establish',
}
ERROR_LIST = '\n'.join(f'- "{k}": {v}' for k, v in ERROR_MEANINGS.items())

MAX_STEPS = 20
MAX_STEP_CHARS = 2000


class PracticeUnavailable(Exception):
    pass


def ask(prompt: str, images: list[tuple[bytes, str]] | None = None) -> dict:
    """One model request (with images, if given); failures become a message
    that says the work is kept."""
    try:
        provider = ai_provider.get_ai_provider()
        data = provider.generate_json_from_images(prompt, images) if images else provider.generate_json(prompt)
    except NotImplementedError as exc:
        raise PracticeUnavailable(_('Reading a photo needs the Gemini provider, which is not the one in use.')) from exc
    except GeminiNotConfiguredError as exc:
        raise PracticeUnavailable(_('This needs the AI provider, which is not available right now.')) from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning('Practice request failed: %s', exc)
        if isinstance(exc, GeminiQuotaError) or is_quota_error(exc):
            raise PracticeUnavailable(_('The AI has used up its free requests for now. Wait a few minutes and try '
                                        'again; what you wrote is kept.')) from exc
        if 'busy' in str(exc).lower() or 'timed out' in str(exc).lower():
            raise PracticeUnavailable(_('The AI took too long to answer. Try again; what you wrote is kept.')) from exc
        raise PracticeUnavailable(_('That could not be done just now. Try again in a minute; what you wrote '
                                    'is kept.')) from exc
    return data if isinstance(data, dict) else {}


def language_of(*texts: str) -> str:
    """'vi' or 'en' (or 'other') from the first text that tells."""
    for text in texts:
        lang = detect_language(text or '')
        if lang != 'other':
            return lang
    return 'other'


def clean_steps(raw) -> list[str]:
    """The student's steps, blank ones dropped, bounded."""
    if not isinstance(raw, list):
        return []
    return [str(s).strip()[:MAX_STEP_CHARS] for s in raw if str(s or '').strip()][:MAX_STEPS]
