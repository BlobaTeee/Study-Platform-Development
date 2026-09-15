import logging

from django.conf import settings
from django.db import transaction
from flashcards.models import Flashcard
from quizzes.models import Quiz, Question
from .gemini_client import (
    GeminiNotConfiguredError,
    GeminiGenerationError,
    GeminiQuotaError,
    is_quota_error,
)
from .ai_provider import get_ai_provider
from . import dedupe, fallback
from .decks import items_with_exact_sources
from .deck_limits import batch_size

logger = logging.getLogger(__name__)

# Values reported back as `generated_by`, so a silent fallback is visible.
BY_EXTRACTIVE_ML = 'extractive-ml'
BY_EXTRACTIVE_FALLBACK = 'extractive-fallback'


def _mark(meta, provider: str, reason: str = ''):
    """Record which generator actually produced the content."""
    if meta is not None:
        meta['provider'] = provider
        if reason:
            meta['reason'] = reason
    return meta


def _fell_back(meta, exc, kind: str):
    """Log + record that we degraded to the extractive pipeline."""
    logger.warning('%s generation fell back to the extractive ML pipeline: %s', kind, exc)
    return _mark(meta, BY_EXTRACTIVE_FALLBACK, str(exc))


def _document_chunks(text: str) -> list[str]:
    """The most informative excerpts of the document, in reading order.

    Generating from one 12k-char prompt truncated long documents and made small
    local models lose the plot; a few focused excerpts cover the whole document
    with prompts a 3B model handles reliably.
    """
    from ml_pipeline.services.chunking import chunk_text, select_chunks
    k = getattr(settings, 'RAG_CHUNKS', 3)
    return select_chunks(chunk_text(text), k=k) or [text[:12000]]


def _generate_over_chunks(provider, chunks, per_chunk, build_prompt, key, limit):
    """Call the provider once per excerpt, aggregating deduped items.

    A failing excerpt is skipped rather than sinking the whole request; only if
    every excerpt fails do we raise, letting the caller fall back.
    """
    items, seen, errors = [], set(), []
    for chunk in chunks:
        try:
            data = provider.generate_json(build_prompt(chunk, per_chunk))
        except Exception as exc:
            logger.warning('Excerpt generation failed (continuing): %s', exc)
            errors.append(exc)
            continue
        for item in (data.get(key) or []):
            dedup = (item.get('question') or item.get('question_text') or '').strip().lower()
            if not dedup or dedup in seen:
                continue
            seen.add(dedup)
            items.append(item)
        if len(items) >= limit:
            break
    if not items and errors:
        raise errors[0]
    return items[:limit]


def _use_local_fallback() -> bool:
    return getattr(settings, 'USE_LOCAL_FALLBACK_ON_QUOTA', True)


def _use_ml_primary() -> bool:
    return getattr(settings, 'USE_ML_PRIMARY', False)


def _sources_text(sources) -> str:
    if not sources:
        raise ValueError('No sources selected.')
    parts = []
    for source in sources:
        if source.status != 'ready' or not source.extracted_text.strip():
            raise ValueError(
                f'Source "{source.title}" has no extracted text. '
                'Wait for processing or use a document with readable text.'
            )
        parts.append(f'### Document: {source.title}\n{source.extracted_text[:18000]}')
    return '\n\n'.join(parts)[:40000]


def _titles_label(sources) -> str:
    if len(sources) == 1:
        return sources[0].title
    return ', '.join(s.title for s in sources[:3]) + (
        f' (+{len(sources) - 3} more)' if len(sources) > 3 else ''
    )


def _generate_flashcards_ml(sources, user, count: int) -> list[Flashcard]:
    from ml.adapter import generate_flashcards_ml
    return generate_flashcards_ml(sources, user, count)


def _generate_quiz_ml(sources, user, question_count: int) -> Quiz:
    from ml.adapter import generate_quiz_ml
    return generate_quiz_ml(sources, user, question_count)


def _save_flashcards_from_json(
    data: dict, user, source_ids: list[int], count: int
) -> list[Flashcard]:
    items = data.get('flashcards') or []
    if not items:
        raise GeminiGenerationError('No flashcards were generated.')

    # Deduped against the batch itself only, not against the cards already on
    # file: those are retired by this generation (see
    # `generate_flashcards_for_sources`), so rejecting a question for matching
    # one of them would silently shrink the replacement deck. Within the batch
    # it still matters — excerpts overlap, so one run can raise a fact twice.
    fresh = dedupe.new_flashcards(items[:count], [])[:count]

    created = []
    for item in fresh:
        question = (item.get('question') or '').strip()
        answer = (item.get('answer') or '').strip()
        difficulty = (item.get('difficulty') or 'medium').lower()
        if difficulty not in ('easy', 'medium', 'hard'):
            difficulty = 'medium'
        if not question or not answer:
            continue
        card = Flashcard.objects.create(
            user=user,
            question=question,
            answer=answer,
            difficulty=difficulty,
            is_public=False,
        )
        created.append(card)

    # Raising rather than returning [] is what lets the caller fall back to the
    # extractive generator. It is also what protects the existing deck: the
    # cards on file are only retired once a replacement batch comes back
    # non-empty, so an empty result here costs the learner nothing.
    if not created:
        raise GeminiGenerationError('No valid flashcards could be saved.')
    return created


def _replace_deck(cards: list[Flashcard], user, source_ids: list[int], notebook) -> None:
    """Hand the new deck its sources and notebook, and retire the deck it replaces.

    All three writes live here rather than at each creation site because
    there are four of them (LLM, ML-primary, local fallback, regeneration) and
    only this one runs for every provider — the local fallback in particular
    generates from a stand-in object that has no notebook or sources to read.

    Retirement is "every other active card of exactly this selection" rather
    than a list captured before generating, so two generations racing each
    other still leave one deck rather than two. Archiving rather than deleting
    keeps the reviews already recorded against those cards, which analytics
    counts.

    Atomic: a crash between the writes would leave the old deck and the new
    one both live, or a new deck with no sources, which is the stacking and
    the orphaning this exists to prevent.
    """
    fresh_ids = [c.id for c in cards]
    Through = Flashcard.sources.through
    with transaction.atomic():
        Through.objects.bulk_create(
            [Through(flashcard_id=cid, source_id=sid)
             for cid in fresh_ids for sid in source_ids],
            ignore_conflicts=True)
        if notebook is not None:
            Flashcard.objects.filter(id__in=fresh_ids).update(notebook=notebook)
            for card in cards:
                card.notebook = notebook
        previous = items_with_exact_sources(
            Through.objects
            .filter(flashcard__user=user, flashcard__archived=False)
            .exclude(flashcard_id__in=fresh_ids)
            .values_list('flashcard_id', 'source_id'),
            source_ids)
        Flashcard.objects.filter(id__in=previous).update(
            archived=True, needs_regeneration=False)


def generate_flashcards_for_sources(sources, user, count: int = 10,
                                    meta: dict | None = None) -> list[Flashcard]:
    """Generate a source selection's flashcards, replacing any it already has.

    Generating used to append, so a document pressed three times carried
    thirty cards and the study queue filled with one subject. It now produces
    one deck of at most `deck_limits.MAX_CARDS_PER_SOURCE`: the old deck is
    retired
    only once a replacement is actually in hand, so a failed generation leaves
    the learner exactly what they had. Pass `meta` to learn which generator
    was used.
    """
    count = batch_size(count)
    source_ids = [s.id for s in sources]
    # Every source in a request belongs to one notebook (the view filters them
    # by it), so the first one names the deck's owner.
    notebook = getattr(sources[0], 'notebook', None) if sources else None

    cards = _generate_flashcards(sources, user, count, source_ids, meta)
    if cards:
        _replace_deck(cards, user, source_ids, notebook)
    return cards


def _generate_flashcards(sources, user, count: int, source_ids: list[int],
                         meta: dict | None) -> list[Flashcard]:
    """Run the provider cascade. Creates cards; does not retire anything."""
    # Validate + guard against thin sources up front, for every provider, so the
    # user gets one clear message instead of empty output or a silent fallback.
    text = _sources_text(sources)
    from ml_pipeline.source_guard import check_source_text, MIN_WORDS_FLASHCARDS
    check_source_text(text, kind='flashcard set', min_words=MIN_WORDS_FLASHCARDS)

    if _use_ml_primary():
        try:
            cards = _generate_flashcards_ml(sources, user, count)
            _mark(meta, BY_EXTRACTIVE_ML)
            return cards
        except Exception as exc:
            if not _use_local_fallback():
                raise GeminiGenerationError(f'ML flashcard generation failed: {exc}') from exc

    label = _titles_label(sources)
    chunks = _document_chunks(text)
    per_chunk = -(-count // len(chunks))  # ceil, so the excerpts cover `count`

    def build_prompt(chunk: str, n: int) -> str:
        return f"""Create exactly {n} study flashcards from this excerpt.
Each flashcard must be answerable from the excerpt alone.

Return ONLY valid JSON:
{{"flashcards": [{{"question": "...", "answer": "...", "difficulty": "easy|medium|hard"}}]}}

Source: {label}
Excerpt:
{chunk}
"""

    try:
        provider = get_ai_provider()
        items = _generate_over_chunks(
            provider, chunks, per_chunk, build_prompt, 'flashcards', count)
        cards = _save_flashcards_from_json({'flashcards': items}, user, source_ids, count)
        _mark(meta, provider.name)
        return cards
    except GeminiNotConfiguredError as exc:
        if _use_local_fallback():
            _fell_back(meta, exc, 'Flashcard')
            return fallback.generate_flashcards_fallback_multi(sources, user, count)
        raise
    except (GeminiQuotaError, GeminiGenerationError) as exc:
        if _use_local_fallback() and (isinstance(exc, GeminiQuotaError) or is_quota_error(exc)):
            _fell_back(meta, exc, 'Flashcard')
            return fallback.generate_flashcards_fallback_multi(sources, user, count)
        if isinstance(exc, GeminiQuotaError):
            raise
        raise GeminiGenerationError(f'Flashcard generation failed: {exc}') from exc
    except Exception as exc:
        if _use_local_fallback():
            _fell_back(meta, exc, 'Flashcard')
            return fallback.generate_flashcards_fallback_multi(sources, user, count)
        raise GeminiGenerationError(f'Content generation failed: {exc}') from exc


def generate_quiz_for_sources(sources, user, question_count: int = 8,
                              meta: dict | None = None) -> Quiz:
    """Generate a quiz. Pass `meta` to learn which generator was used."""
    question_count = max(4, min(question_count, 15))
    source_ids = [s.id for s in sources]

    # Validate + guard against thin sources up front, for every provider, so the
    # user gets one clear message instead of empty output or a silent fallback.
    text = _sources_text(sources)
    from ml_pipeline.source_guard import check_source_text, MIN_WORDS_QUIZ
    check_source_text(text, kind='quiz', min_words=MIN_WORDS_QUIZ)

    if _use_ml_primary():
        try:
            quiz = _generate_quiz_ml(sources, user, question_count)
            _mark(meta, BY_EXTRACTIVE_ML)
            return quiz
        except Exception as exc:
            if not _use_local_fallback():
                raise GeminiGenerationError(f'ML quiz generation failed: {exc}') from exc

    label = _titles_label(sources)
    chunks = _document_chunks(text)
    per_chunk = -(-question_count // len(chunks))  # ceil, so excerpts cover the count

    def build_prompt(chunk: str, n: int) -> str:
        return f"""Create exactly {n} multiple-choice questions from this excerpt.
For each question give: the question, the single correct answer, and exactly 3
plausible but incorrect answers (distractors) on the same topic. Do NOT put the
correct answer in the distractors, and make the distractors distinct.
Each question must be answerable from the excerpt alone.

Return ONLY valid JSON in exactly this shape:
{{"questions": [{{"question_text": "...", "correct_answer": "...", "distractors": ["...", "...", "..."], "explanation": "..."}}]}}

Source: {label}
Excerpt:
{chunk}
"""

    try:
        provider = get_ai_provider()
        questions_data = _generate_over_chunks(
            provider, chunks, per_chunk, build_prompt, 'questions', question_count)
        _mark(meta, provider.name)
    except GeminiNotConfiguredError as exc:
        if _use_local_fallback():
            _fell_back(meta, exc, 'Quiz')
            return fallback.generate_quiz_fallback_multi(sources, user, question_count)
        raise
    except (GeminiQuotaError, GeminiGenerationError) as exc:
        if _use_local_fallback() and (isinstance(exc, GeminiQuotaError) or is_quota_error(exc)):
            _fell_back(meta, exc, 'Quiz')
            return fallback.generate_quiz_fallback_multi(sources, user, question_count)
        if isinstance(exc, GeminiQuotaError):
            raise
        raise GeminiGenerationError(f'Quiz generation failed: {exc}') from exc
    except Exception as exc:
        if _use_local_fallback():
            _fell_back(meta, exc, 'Quiz')
            return fallback.generate_quiz_fallback_multi(sources, user, question_count)
        raise GeminiGenerationError(f'Content generation failed: {exc}') from exc

    if not questions_data:
        raise GeminiGenerationError('No quiz questions were generated.')

    # Titled locally: questions come from several excerpts, so there is no single
    # model-authored title to use.
    title = f'Quiz: {label}' if len(sources) == 1 else f'Quiz: {len(sources)} sources'
    quiz = Quiz.objects.create(
        user=user,
        title=title[:255],
        description=f'Generated from {label}'[:2000],
        time_limit=0,
        is_public=False,
        is_published=True,
    )

    quiz.sources.set(source_ids)

    import random
    from .quiz_shaping import shape_quiz_question
    rng = random.Random(42)

    order = 0
    for q in questions_data[:question_count]:
        shaped = shape_quiz_question(q, rng)
        if shaped is None:
            continue  # unanswerable (no question/answer/distractor) -> skip

        Question.objects.create(
            quiz=quiz,
            question_text=shaped['question_text'],
            question_type=shaped['question_type'],
            options=shaped['options'],
            correct_answer=shaped['correct_answer'],
            explanation=shaped['explanation'],
            order=order,
        )
        order += 1

    if order == 0:
        quiz.delete()
        raise GeminiGenerationError('No valid questions could be saved.')

    return quiz


def generate_flashcards_for_source(source, user, count: int = 10) -> list[Flashcard]:
    return generate_flashcards_for_sources([source], user, count=count)


def generate_quiz_for_source(source, user, question_count: int = 8) -> Quiz:
    return generate_quiz_for_sources([source], user, question_count=question_count)
