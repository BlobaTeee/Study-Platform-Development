"""A tutor for one card, after the answer is showing.

Not a chatbot over the documents: it appears only once the student has
tried to recall and seen the back of the card, it answers from the passage
the card came from, and it gets three questions per card. When the passage
does not cover the question it says so rather than filling the gap.
"""
import logging

from django.utils.translation import gettext as _

from ml_pipeline.language import detect_language, language_name
from notebooks.services.ai_provider import get_ai_provider
from notebooks.services.gemini_client import GeminiNotConfiguredError
from notebooks.services.writing_style import WRITING_STYLE, tidy_prose

logger = logging.getLogger(__name__)

MAX_TURNS = 3            # questions per card per session
MAX_QUESTION_CHARS = 500
MAX_PASSAGE_CHARS = 2500


class TutorUnavailable(Exception):
    pass


def passage_for(card) -> str:
    """The chunk of the card's sources most like the card itself."""
    from ml_pipeline.services.chunking import chunk_text
    candidates = []
    for src in card.sources.all():
        text = (src.extracted_text or '')[:18000]
        candidates.extend(chunk_text(text) or ([text[:MAX_PASSAGE_CHARS]] if text.strip() else []))
    if not candidates:
        return ''
    if len(candidates) == 1:
        return candidates[0][:MAX_PASSAGE_CHARS]
    from sklearn.feature_extraction.text import TfidfVectorizer
    vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5), sublinear_tf=True)
    mat = vec.fit_transform([f'{card.question} {card.answer}'] + candidates)
    sims = (mat[0] @ mat[1:].T).toarray().ravel()
    return candidates[int(sims.argmax())][:MAX_PASSAGE_CHARS]


def ask(card, question: str, history: list[dict]) -> str:
    """`history` is prior turns [{role: 'user'|'tutor', text}] for this card."""
    passage = passage_for(card)
    # The student's language wins: a Vietnamese question about an English
    # paper wants a Vietnamese answer. Too short to tell → the passage's.
    lang = detect_language(question)
    if lang == 'other':
        lang = detect_language(passage or f'{card.question} {card.answer}')
    grounding = (f'Passage from the student\'s own material:\n{passage}'
                 if passage else
                 'No passage is available for this card. Answer from the card alone and say '
                 'plainly when you would only be guessing.')
    turns = '\n'.join(
        f"{'Student' if t.get('role') == 'user' else 'Tutor'}: {str(t.get('text') or '').strip()[:MAX_QUESTION_CHARS]}"
        for t in history if str(t.get('text') or '').strip())
    prompt = f"""You are a patient tutor. A student is reviewing a flashcard, has seen the answer, and
still has a question. Answer in {language_name(lang)}, in at most 4 sentences, using ONLY the
passage below. If the passage does not cover the question, say so in one sentence; do not
invent facts or cite anything the passage does not say. No greeting, no "great question".

Flashcard front: {card.question}
Flashcard back: {card.answer}

{grounding}

{('Earlier in this conversation:' + chr(10) + turns + chr(10)) if turns else ''}Student asks: {question}

{WRITING_STYLE}

Return ONLY valid JSON: {{"answer": "..."}}"""

    try:
        data = get_ai_provider().generate_json(prompt)
    except GeminiNotConfiguredError as exc:
        raise TutorUnavailable(_('The tutor needs the AI provider, which is not available right now.')) from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning('Tutor failed: %s', exc)
        raise TutorUnavailable(_('The tutor could not answer just now. Try again in a minute.')) from exc
    answer = tidy_prose(str(data.get('answer') or ''))
    if not answer:
        raise TutorUnavailable(_('The tutor could not answer just now. Try again in a minute.'))
    return answer[:1500]
