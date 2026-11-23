"""What the problem writer and the grader share: the error vocabulary, the
model call with failures a student can act on, and the language to write in."""
import logging
import re
import time

from django.utils.translation import gettext as _

from ml_pipeline.language import detect_language
from notebooks.services import ai_provider
from notebooks.services.gemini_client import GeminiNotConfiguredError, GeminiQuotaError, is_quota_error
from notebooks.services.model_lane import long_read, quick as quick_lane

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

MAX_STEPS = 40
MAX_STEP_CHARS = 2000
#: The answer box's limit. Must match MAX_ANSWER_CHARS in lib/practice.ts.
MAX_ANSWER_CHARS = 4000


class PracticeUnavailable(Exception):
    pass


RETRY_PAUSE_SECONDS = 1.0


def _transient(exc: Exception) -> bool:
    """A dropped connection, worth one more try: not a refusal, a quota or
    a timeout, which say something about the request or the model."""
    try:
        import httpx
        if isinstance(exc, httpx.TransportError) and not isinstance(exc, httpx.TimeoutException):
            return True
    except ImportError:  # pragma: no cover
        pass
    if isinstance(exc, (ConnectionError, BrokenPipeError)):
        return True
    text = str(exc).lower()
    return any(s in text for s in ('connection reset', 'connection aborted', 'server disconnected',
                                   'remote end closed', 'broken pipe'))


def ask(prompt: str, images: list[tuple[bytes, str]] | None = None, quick: bool = False,
        reading: bool = False, long: bool = False) -> dict:
    """One model request (with images, if given); failures become a message
    the student can act on. `quick` puts it on the fast model first
    (model_lane), for a judgement the student is waiting on. `reading` is a
    photo or file being read: nothing the student wrote is at stake, so the
    message does not promise to keep it. `long` is a long answer that still
    needs thinking (several answer keys at once): it is given the reading
    deadline, and nothing typed is at stake either. A dropped connection is
    tried once more before it counts as a failure."""
    def call():
        provider = ai_provider.get_ai_provider()
        if quick:
            with quick_lane():
                return provider.generate_json(prompt)
        if reading or long:
            with long_read(think_less=reading):
                return provider.generate_json_from_images(prompt, images) if images else provider.generate_json(prompt)
        return provider.generate_json_from_images(prompt, images) if images else provider.generate_json(prompt)

    try:
        try:
            data = call()
        except Exception as exc:  # noqa: BLE001
            if not _transient(exc):
                raise
            logger.warning('Practice request dropped, trying once more: %s', exc)
            time.sleep(RETRY_PAUSE_SECONDS)
            data = call()
    except NotImplementedError as exc:
        raise PracticeUnavailable(_('Reading a photo needs the Gemini provider, which is not the one in use.')) from exc
    except GeminiNotConfiguredError as exc:
        raise PracticeUnavailable(_('This needs the AI provider, which is not available right now.')) from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning('Practice request failed: %s', exc)
        typed = not (reading or long)        # the message promises to keep what was typed
        if isinstance(exc, GeminiQuotaError) or is_quota_error(exc):
            raise PracticeUnavailable(
                _('The AI has used up its free requests for now. Wait a few minutes and try again.') if not typed
                else _('The AI has used up its free requests for now. Wait a few minutes and try '
                       'again; what you wrote is kept.')) from exc
        text = str(exc).lower()
        if '503' in text or 'overloaded' in text or 'unavailable' in text:
            raise PracticeUnavailable(
                _('The AI is overloaded right now. Try again in a few minutes.') if not typed
                else _('The AI is overloaded right now. Try again in a few minutes; what you wrote is kept.')) from exc
        if 'busy' in text or 'timed out' in text:
            raise PracticeUnavailable(
                _('The AI took too long to read the problems. Try again.') if reading
                else _('The AI took too long to answer. Try again.') if long
                else _('The AI took too long to answer. Try again; what you wrote is kept.')) from exc
        raise PracticeUnavailable(
            _('The problems could not be read just now. Try again in a minute.') if not typed
            else _('That could not be done just now. Try again in a minute; what you wrote is kept.')) from exc
    if isinstance(data, list):
        # Asked for {"questions": [...]}, a model sometimes sends the list alone.
        return {'items': data}
    return data if isinstance(data, dict) else {}


def items_of(reply: dict, key: str) -> list:
    """The list a reply was asked to hold under `key`, or the bare list the
    model sent instead."""
    for value in (reply.get(key), reply.get('items')):
        if isinstance(value, list):
            return value
    return []


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


# A full stop, question mark or ellipsis (with any closing quote or bracket)
# that is followed by a space: the only places a sentence can end inside a
# line. Whether it does is decided by what comes next, in split_sentences.
_END = re.compile(r'[.!?…]+["”’»)\]]*(?=\s)')
# A list marker on its own ("1.", "b)") belongs to the sentence after it.
_MARKER = re.compile(r'^(?:\d{1,2}|[a-zA-Z])[.)]$')
# Short forms that end in a full stop but not a sentence, and initials ("H.").
_ABBREVIATION = re.compile(
    r'(?:^|[\s(])(?:TP|Tp|Q|P|Mr|Mrs|Ms|Dr|St|No|Fig|Eq|vs|etc|e\.g|i\.e|TS|ThS|PGS|GS|v\.v|vd|VD|Vd|tr|cf)\.$'
    r'|(?:^|\s)[A-ZĐ]\.$')


def split_sentences(text: str) -> list[str]:
    """The student's answer as numbered sentences, for the grader to point at.

    A new line always starts a sentence; inside a line a sentence ends at
    . ? ! or … followed by a space, whatever case comes next (students who
    type fast often skip capitals). "TP.HCM", "3.14" and "1,5 m" have no
    space after the stop, and short forms such as "v.v.", "VD." or an
    initial are not ends. Past MAX_STEPS sentences the rest is kept together
    in the last one.
    """
    out: list[str] = []
    for line in (text or '').splitlines():
        line = line.strip()
        start = 0
        for m in _END.finditer(line):
            if not line[m.end():].strip():
                continue
            piece = line[start:m.end()].strip()
            if _MARKER.match(piece) or _ABBREVIATION.search(piece):
                continue
            out.append(piece)
            start = m.end()
        tail = line[start:].strip()
        if tail:
            out.append(tail)
    out = [s[:MAX_STEP_CHARS] for s in out if s]
    if len(out) > MAX_STEPS:
        out = out[:MAX_STEPS - 1] + [' '.join(out[MAX_STEPS - 1:])[:MAX_STEP_CHARS]]
    return out


def answer_from(data) -> tuple[list[str], str]:
    """(sentences, the answer as written) from a request: the answer box's
    "text", or, from an older page, a list of "steps"."""
    text = data.get('text') if hasattr(data, 'get') else None
    if isinstance(text, str) and text.strip():
        text = text.strip()[:MAX_ANSWER_CHARS]
        return split_sentences(text), text
    return clean_steps(data.get('steps') if hasattr(data, 'get') else None), ''
