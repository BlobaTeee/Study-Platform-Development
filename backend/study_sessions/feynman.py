"""Giải thích bằng lời của bạn — the Feynman technique on a concept the
student keeps forgetting.

The feedback is judged against the passages the cards came from, never
general knowledge: a point the material does not make is neither "missing"
nor "wrong", it is outside what the student is studying. It comes back as
what was right, what is missing, what is wrong and where to reread, in
words, with no score.
"""
import logging

from django.utils.translation import gettext as _

from ml_pipeline.language import detect_language, language_name
from notebooks.services.ai_provider import get_ai_provider
from notebooks.services.gemini_client import GeminiNotConfiguredError

from .models import FeynmanAttempt

logger = logging.getLogger(__name__)

MIN_CHARS = 20          # fewer and there is nothing to judge
MAX_CHARS = 4000
MAX_CARDS = 30
MAX_PASSAGES = 3
MAX_PASSAGE_CHARS = 2500
MAX_POINTS = 5
LEVELS = ('solid', 'most', 'reread')


class ExplainUnavailable(Exception):
    pass


def card_key(ids) -> str:
    return ','.join(str(i) for i in sorted(set(ids)))


def passages_for(cards) -> list[dict]:
    """The chunk of each card's sources most like the card, once each."""
    from ml_pipeline.services.chunking import chunk_text
    from sklearn.feature_extraction.text import TfidfVectorizer

    chunks: dict[int, list[str]] = {}
    out, seen = [], set()
    for card in cards:
        candidates = []
        for src in card.sources.all():
            if src.id not in chunks:
                text = (src.extracted_text or '')[:18000]
                chunks[src.id] = chunk_text(text) or ([text[:MAX_PASSAGE_CHARS]] if text.strip() else [])
            candidates.extend((src, c) for c in chunks[src.id])
        if not candidates:
            continue
        if len(candidates) == 1:
            src, passage = candidates[0]
        else:
            vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5), sublinear_tf=True)
            mat = vec.fit_transform([f'{card.question} {card.answer}'] + [c for _, c in candidates])
            src, passage = candidates[int((mat[0] @ mat[1:].T).toarray().ravel().argmax())]
        key = passage.strip()[:200]
        if key in seen:
            continue
        seen.add(key)
        out.append({'source_id': src.id, 'notebook_id': src.notebook_id, 'title': src.title,
                    'passage': passage[:MAX_PASSAGE_CHARS]})
        if len(out) == MAX_PASSAGES:
            break
    return out


def explain(user, cards, concept: str, text: str) -> FeynmanAttempt:
    passages = passages_for(cards)
    lang = detect_language(text)
    if lang == 'other':
        lang = detect_language(' '.join(p['passage'] for p in passages) or concept)
    numbered = '\n\n'.join(f'[{i}] {p["passage"]}' for i, p in enumerate(passages, 1))
    flashcards = '\n'.join(f'- {c.question} — {c.answer}' for c in cards[:12])
    prompt = f"""A student is using the Feynman technique: they explained a concept in their own words,
as if teaching someone who has not studied it. Give feedback in {language_name(lang)}.

Judge ONLY against the passages below, which are the student's own study material. A point
the passages do not make is neither missing nor wrong. Be specific and kind; no greeting,
no praise for effort, and never repeat the student's explanation back to them.

- "correct": points the student made that the passages support (at most {MAX_POINTS}).
- "missing": the important points about this concept in the passages that the student left
  out (at most {MAX_POINTS}, most important first).
- "wrong": claims that contradict the passages, each with a short correction.
- "level": "solid" if nothing important is missing or wrong, "most" if the core is right but
  something is missing, "reread" if the core is missing or wrong.
- "reread": the numbers of the passages the student should read again.

Concept: {concept}

Flashcards on this concept:
{flashcards}

Passages:
{numbered or '(none available — judge from the flashcards alone)'}

Student's explanation:
{text}

Return ONLY valid JSON:
{{"correct": ["..."], "missing": ["..."], "wrong": [{{"claim": "...", "correction": "..."}}], "level": "solid|most|reread", "reread": [1]}}"""

    try:
        data = get_ai_provider().generate_json(prompt)
    except GeminiNotConfiguredError as exc:
        raise ExplainUnavailable(_('Feedback needs the AI provider, which is not available right now.')) from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning('Feynman feedback failed: %s', exc)
        raise ExplainUnavailable(_('Feedback could not be written just now. Try again in a minute.')) from exc

    return FeynmanAttempt.objects.create(
        user=user, card_key=card_key(c.id for c in cards), concept=concept,
        text=text, feedback=clean(data, passages))


def clean(data, passages: list[dict]) -> dict:
    """The model's reply in a shape the page can trust."""
    data = data if isinstance(data, dict) else {}
    correct = _points(data.get('correct'))
    missing = _points(data.get('missing'))
    wrong = [{'claim': str(w['claim']).strip()[:300], 'correction': str(w['correction']).strip()[:300]}
             for w in (data.get('wrong') if isinstance(data.get('wrong'), list) else [])
             if isinstance(w, dict) and str(w.get('claim') or '').strip()
             and str(w.get('correction') or '').strip()][:MAX_POINTS]
    level = data.get('level')
    if level not in LEVELS:
        # Read the verdict off the feedback itself rather than guess.
        level = 'solid' if not (missing or wrong) else 'reread' if len(wrong) >= 2 or len(missing) >= 3 else 'most'
    picked = data.get('reread') if isinstance(data.get('reread'), list) else []
    reread = [passages[n - 1] for n in dict.fromkeys(picked)
              if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= len(passages)]
    return {'correct': correct, 'missing': missing, 'wrong': wrong, 'level': level, 'reread': reread}


def _points(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip()[:300] for v in value if isinstance(v, str) and v.strip()][:MAX_POINTS]


def payload(attempt: FeynmanAttempt) -> dict:
    return {'id': attempt.id, 'concept': attempt.concept, 'text': attempt.text,
            'created_at': attempt.created_at, **attempt.feedback}
