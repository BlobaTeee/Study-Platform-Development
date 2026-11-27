"""Why a wrong answer was wrong, in the student's own material's words.

Two or three sentences: what the passage actually says, why the chosen
option does not fit it, in the language of the passage. No passage (an old
question) → the model is told so and asked to stay general rather than
invent a citation.
"""
import logging

from django.utils.translation import gettext as _

from ml_pipeline.language import detect_language, language_name
from notebooks.services.ai_provider import get_ai_provider
from notebooks.services.model_lane import quick
from notebooks.services.writing_style import WRITING_STYLE, tidy_prose
from notebooks.services.gemini_client import GeminiNotConfiguredError

logger = logging.getLogger(__name__)


class ExplainUnavailable(Exception):
    pass


def explain_miss(row) -> str:
    """`row` is a MockTestQuestion answered wrong. Returns the explanation
    and stores it on the row; a stored one is returned as is."""
    if row.ai_explanation:
        return row.ai_explanation

    excerpt = (row.source_excerpt or '').strip()
    lang = detect_language(excerpt or row.question_text)
    options = '\n'.join(f'- {o}' for o in (row.options or []))
    grounding = (f'Passage the question was written from:\n{excerpt}'
                 if excerpt else
                 'No passage is available for this question; explain from the question and '
                 'answers alone, and do not claim what a text says.')
    prompt = f"""A student answered a quiz question wrong. In 2 or 3 sentences, in {language_name(lang)},
explain what the correct answer is and why the student's choice does not fit, using only what
the passage says. Do not repeat the question.

Question: {row.question_text}
Options:
{options}
Correct answer: {row.correct_answer}
Student answered: {row.user_answer or "(left blank)"}

{grounding}

{WRITING_STYLE}

Return ONLY valid JSON: {{"explanation": "..."}}"""

    try:
        with quick():
            data = get_ai_provider().generate_json(prompt)
    except GeminiNotConfiguredError as exc:
        raise ExplainUnavailable(_('Explanations need the AI provider, which is not available right now.')) from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning('Explain failed: %s', exc)
        raise ExplainUnavailable(_('Could not write an explanation. Try again in a minute.')) from exc

    text = tidy_prose(str(data.get('explanation') or ''),
                      source_title=row.source.title if row.source_id else '')
    if not text:
        raise ExplainUnavailable(_('Could not write an explanation. Try again in a minute.'))
    row.ai_explanation = text[:2000]
    row.save(update_fields=['ai_explanation'])
    return row.ai_explanation
