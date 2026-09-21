"""A fresh paper on one concept the student keeps missing.

The model gets the passages those questions came from (their stored
excerpts; for older questions without one, the source chunk most like the
question) and the questions themselves — so it writes new ones on the same
concept from other angles rather than paraphrasing the misses. The quiz is
published and tagged with its sources so the study page and the mock-test
pool pick it up, but nothing already there is retired.
"""
import logging
import random

from django.utils.translation import gettext as _

from ml_pipeline.language import detect_language, language_name
from notebooks.services.ai_provider import get_ai_provider
from notebooks.services.gemini_client import GeminiNotConfiguredError
from notebooks.services.provenance import excerpt_of
from notebooks.services.quiz_shaping import shape_quiz_question
from quizzes.models import Question, Quiz

logger = logging.getLogger(__name__)

PRACTICE_COUNT = 5
# Ask for more than we keep: small models reword a few misses whatever they
# are told, and the guard below throws those away.
ASK_FOR = PRACTICE_COUNT + 3
MAX_PASSAGE_CHARS = 6000
# A generated question at least this similar to a missed one is a reword,
# not practice. 0.75 on difflib's ratio catches "for homeless young people"
# vs "for homeless youth"; two questions on the same fact from different
# angles sit well under it.
REWORD_RATIO = 0.75
MIN_NOVEL = 2


class PracticeUnavailable(Exception):
    """No provider can write the paper right now."""


def passages_for(questions, sources) -> list[tuple[int | None, str]]:
    """(source_id, passage) per distinct passage the concept lives in."""
    from ml_pipeline.services.chunking import chunk_text
    seen, out = set(), []
    chunk_cache: dict[int, list[str]] = {}

    def chunks_of(source):
        if source.id not in chunk_cache:
            chunk_cache[source.id] = chunk_text(source.extracted_text[:18000]) or [source.extracted_text[:4000]]
        return chunk_cache[source.id]

    for q in questions:
        if q.source_excerpt:
            passage, sid = q.source_excerpt, q.source_id
        else:
            # Older questions carry no excerpt: take the chunk most like the
            # question from its source, or from every source in the notebook.
            candidates = [(s.id, c) for s in ([q.source] if q.source_id else sources) for c in chunks_of(s)]
            if not candidates:
                continue
            sid, passage = _closest(q.question_text + ' ' + q.correct_answer, candidates)
        key = passage.strip()[:200]
        if key and key not in seen:
            seen.add(key)
            out.append((sid, passage))
    return out


def _closest(text: str, candidates: list[tuple[int, str]]) -> tuple[int, str]:
    from sklearn.feature_extraction.text import TfidfVectorizer
    vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5), sublinear_tf=True)
    mat = vec.fit_transform([text] + [c for _, c in candidates])
    sims = (mat[0] @ mat[1:].T).toarray().ravel()
    return candidates[int(sims.argmax())]


def _norm(text: str) -> str:
    return ' '.join((text or '').lower().replace('?', '').split())


def novel_questions(generated: list[dict], missed_texts: list[str]) -> list[dict]:
    """Drop generated questions that merely reword a missed one. Small
    models copy the list they were told not to copy; this is the guard."""
    from difflib import SequenceMatcher
    missed = [_norm(t) for t in missed_texts]
    kept = []
    for item in generated:
        text = _norm(item.get('question_text') or item.get('question') or '')
        if not text:
            continue
        if any(SequenceMatcher(None, text, m).ratio() >= REWORD_RATIO for m in missed):
            continue
        kept.append(item)
    return kept


def generate_practice_quiz(user, notebook, label: str, questions) -> Quiz:
    sources = list(notebook.sources.all())
    passages = passages_for(questions, sources)
    if not passages:
        raise PracticeUnavailable(_('These questions have no source text to practise from.'))

    joined, used_sources = [], []
    for sid, passage in passages:
        if sum(len(p) for p in joined) + len(passage) > MAX_PASSAGE_CHARS:
            break
        joined.append(passage)
        if sid and sid not in used_sources:
            used_sources.append(sid)
    passage_text = '\n\n'.join(joined)
    lang = detect_language(passage_text)
    missed = '\n'.join(f'- {q.question_text}' for q in questions[:10])

    prompt = f"""A student keeps getting questions about "{label}" wrong. Write exactly {ASK_FOR}
NEW multiple-choice questions on this concept, each about a different fact or a different
angle (why, how, what follows, compare), so that answering them proves the student now
understands it. Write in {language_name(lang)}, the language of the passage. Each question
must be answerable from the passage alone.

For each question give: the question, the single correct answer, exactly 3 plausible but
clearly wrong distractors (never a synonym of the correct answer), and a one-sentence
explanation. Plain text, no "A)" prefixes.

Passage:
{passage_text}

Already asked — do NOT repeat or reword any of these:
{missed}

Return ONLY valid JSON in exactly this shape:
{{"questions": [{{"question_text": "...", "correct_answer": "...", "distractors": ["...", "...", "..."], "explanation": "..."}}]}}"""

    missed_texts = [q.question_text for q in questions]
    fresh: list[dict] = []
    for attempt in range(2):
        try:
            data = get_ai_provider().generate_json(prompt)
        except GeminiNotConfiguredError as exc:
            raise PracticeUnavailable(_('Practice needs the AI provider, which is not available right now.')) from exc
        except Exception as exc:  # noqa: BLE001 — bad JSON from a small model is routine; one more go
            logger.warning('Practice generation attempt %d failed: %s', attempt + 1, exc)
            continue
        got = novel_questions(data.get('questions') or [], missed_texts)
        if len(got) > len(fresh):
            fresh = got
        if len(fresh) >= MIN_NOVEL:
            break
        # The model parroted the misses: say so once, plainly, and retry.
        prompt += ('\n\nYour previous answer repeated the missed questions almost word for word. '
                   'Ask about DIFFERENT facts from the passage, or the same facts framed as '
                   'why/how/compare questions.')

    rng = random.Random(42)
    shaped = [s for s in (shape_quiz_question(q, rng) for q in fresh) if s]
    if not shaped:
        raise PracticeUnavailable(_('Could not write the practice questions. Try again in a minute.'))

    quiz = Quiz.objects.create(
        user=user, title=f'Practice: {label}'[:255],
        description=_('Practice on a concept you kept missing')[:2000],
        time_limit=0, is_public=False, is_published=True,
    )
    quiz.sources.set(used_sources or [s.id for s in sources])
    # Provenance: the concept's first passage stands for the paper — each
    # question was written from the joined passages, not one chunk.
    first_sid = used_sources[0] if used_sources else None
    for i, s in enumerate(shaped[:PRACTICE_COUNT]):
        Question.objects.create(
            quiz=quiz, order=i, question_text=s['question_text'], question_type=s['question_type'],
            options=s['options'], correct_answer=s['correct_answer'], explanation=s['explanation'],
            source_id=first_sid, source_excerpt=excerpt_of(joined[0]),
        )
    return quiz
