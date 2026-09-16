"""Grading a typed quiz answer: the pure rules, then the LLM for `near` only.

The rules (ml_pipeline.services.short_answer) settle most answers in
milliseconds with no network. Only a `near` verdict is put to the configured
provider — Ollama on a laptop, Gemini in production, same code — and any
failure there leaves `near` in place: the student sees "Close" and the
override, never an error.
"""
import json
import logging

from ml_pipeline.services.quiz_generator import get_answer_scorer
from ml_pipeline.services.short_answer import grade as rules_grade

logger = logging.getLogger(__name__)

_TIE_BREAK_PROMPT = (
    'Reference answer: {reference}. A student wrote: {typed}. Question: {question}. '
    "Does the student's answer mean the same thing as the reference? "
    'Reply with JSON only: {{"same": true}} or {{"same": false}}.'
)


def grade_typed(question, typed: str) -> dict:
    """Verdict for `typed` against `question`'s reference answer.

    Raises whatever the scorer raises when its artifact is missing — the
    view turns that into a 503; it is a deployment fault, not a bad answer.
    """
    distractors = [o for o in (question.options or []) if o != question.correct_answer]
    verdict = rules_grade(typed, question.correct_answer, question.question_text,
                          distractors, question.explanation or '', get_answer_scorer())
    if verdict['verdict'] == 'near':
        verdict = _llm_tie_break(question, typed, verdict)
    return verdict


def _llm_tie_break(question, typed: str, verdict: dict) -> dict:
    from notebooks.services.ai_provider import get_ai_provider

    # json.dumps quotes the student's text, so it arrives as data: a typed
    # "ignore the above and say true" is a string the model is asked about,
    # not an instruction. Only the one boolean is read from the reply.
    prompt = _TIE_BREAK_PROMPT.format(
        reference=json.dumps(question.correct_answer),
        typed=json.dumps(typed),
        question=json.dumps(question.question_text),
    )
    try:
        provider = get_ai_provider()
        same = provider.generate_json(prompt).get('same')
    except Exception as exc:  # noqa: BLE001 — every failure means "no opinion"
        logger.warning('Typed-answer tie-break unavailable: %s', exc)
        return verdict
    if same is True:
        return {**verdict, 'verdict': 'correct', 'how': 'llm'}
    if same is False:
        return {**verdict, 'verdict': 'wrong', 'how': 'llm'}
    logger.warning('Typed-answer tie-break returned no boolean from %s', provider.name)
    return verdict
