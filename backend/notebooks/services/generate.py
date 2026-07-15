import logging

from django.conf import settings
from flashcards.models import Flashcard
from quizzes.models import Quiz, Question
from .gemini_client import (
    GeminiNotConfiguredError,
    GeminiGenerationError,
    GeminiQuotaError,
    is_quota_error,
)
from .ai_provider import get_ai_provider
from . import fallback

logger = logging.getLogger(__name__)

SOURCE_TAG_PREFIX = 'source:'

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


def _use_local_fallback() -> bool:
    return getattr(settings, 'USE_LOCAL_FALLBACK_ON_QUOTA', True)


def _use_ml_primary() -> bool:
    return getattr(settings, 'USE_ML_PRIMARY', False)


def combined_source_tag(source_ids: list[int]) -> str:
    sorted_ids = sorted({int(i) for i in source_ids})
    return f'{SOURCE_TAG_PREFIX}{",".join(str(i) for i in sorted_ids)}'


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


def _generate_flashcards_ml(sources, user, count: int, tag: str) -> list[Flashcard]:
    from ml.adapter import generate_flashcards_ml
    return generate_flashcards_ml(sources, user, count, tag)


def _generate_quiz_ml(sources, user, question_count: int, tag: str) -> Quiz:
    from ml.adapter import generate_quiz_ml
    return generate_quiz_ml(sources, user, question_count, tag)


def _save_flashcards_from_json(
    data: dict, user, source_ids: list[int], count: int
) -> list[Flashcard]:
    items = data.get('flashcards') or []
    if not items:
        raise GeminiGenerationError('No flashcards were generated.')

    tag = combined_source_tag(source_ids)
    created = []
    for item in items[:count]:
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
            tags=tag,
            is_public=False,
        )
        created.append(card)

    if not created:
        raise GeminiGenerationError('No valid flashcards could be saved.')
    return created


def generate_flashcards_for_sources(sources, user, count: int = 10,
                                    meta: dict | None = None) -> list[Flashcard]:
    """Generate flashcards. Pass `meta` to learn which generator was used."""
    count = max(3, min(count, 20))
    source_ids = [s.id for s in sources]
    tag = combined_source_tag(source_ids)

    # Validate + guard against thin sources up front, for every provider, so the
    # user gets one clear message instead of empty output or a silent fallback.
    text = _sources_text(sources)
    from ml_pipeline.source_guard import check_source_text, MIN_WORDS_FLASHCARDS
    check_source_text(text, kind='flashcard set', min_words=MIN_WORDS_FLASHCARDS)

    if _use_ml_primary():
        try:
            cards = _generate_flashcards_ml(sources, user, count, tag)
            _mark(meta, BY_EXTRACTIVE_ML)
            return cards
        except Exception as exc:
            if not _use_local_fallback():
                raise GeminiGenerationError(f'ML flashcard generation failed: {exc}') from exc

    label = _titles_label(sources)
    doc_note = 'multiple documents' if len(sources) > 1 else 'this document'

    prompt = f"""Create exactly {count} study flashcards from {doc_note}.
Combine and synthesize information across all documents where relevant.

Return ONLY valid JSON:
{{"flashcards": [{{"question": "...", "answer": "...", "difficulty": "easy|medium|hard"}}]}}

Sources: {label}
Text:
{text[:12000]}
"""

    try:
        provider = get_ai_provider()
        data = provider.generate_json(prompt)
        cards = _save_flashcards_from_json(data, user, source_ids, count)
        _mark(meta, provider.name)
        return cards
    except GeminiNotConfiguredError as exc:
        if _use_local_fallback():
            _fell_back(meta, exc, 'Flashcard')
            return fallback.generate_flashcards_fallback_multi(sources, user, count, tag)
        raise
    except (GeminiQuotaError, GeminiGenerationError) as exc:
        if _use_local_fallback() and (isinstance(exc, GeminiQuotaError) or is_quota_error(exc)):
            _fell_back(meta, exc, 'Flashcard')
            return fallback.generate_flashcards_fallback_multi(sources, user, count, tag)
        if isinstance(exc, GeminiQuotaError):
            raise
        raise GeminiGenerationError(f'Flashcard generation failed: {exc}') from exc
    except Exception as exc:
        if _use_local_fallback():
            _fell_back(meta, exc, 'Flashcard')
            return fallback.generate_flashcards_fallback_multi(sources, user, count, tag)
        raise GeminiGenerationError(f'Content generation failed: {exc}') from exc


def generate_quiz_for_sources(sources, user, question_count: int = 8,
                              meta: dict | None = None) -> Quiz:
    """Generate a quiz. Pass `meta` to learn which generator was used."""
    question_count = max(4, min(question_count, 15))
    source_ids = [s.id for s in sources]
    tag = combined_source_tag(source_ids)

    # Validate + guard against thin sources up front, for every provider, so the
    # user gets one clear message instead of empty output or a silent fallback.
    text = _sources_text(sources)
    from ml_pipeline.source_guard import check_source_text, MIN_WORDS_QUIZ
    check_source_text(text, kind='quiz', min_words=MIN_WORDS_QUIZ)

    if _use_ml_primary():
        try:
            quiz = _generate_quiz_ml(sources, user, question_count, tag)
            _mark(meta, BY_EXTRACTIVE_ML)
            return quiz
        except Exception as exc:
            if not _use_local_fallback():
                raise GeminiGenerationError(f'ML quiz generation failed: {exc}') from exc

    label = _titles_label(sources)
    doc_note = 'multiple documents' if len(sources) > 1 else 'this document'

    prompt = f"""Create a quiz with {question_count} multiple-choice questions from {doc_note}.
For each question give: the question, the single correct answer, and exactly 3
plausible but incorrect answers (distractors) on the same topic. Do NOT put the
correct answer in the distractors, and make the distractors distinct.

Return ONLY valid JSON in exactly this shape:
{{"title": "...", "description": "...", "questions": [{{"question_text": "...", "correct_answer": "...", "distractors": ["...", "...", "..."], "explanation": "..."}}]}}

Sources: {label}
Text:
{text[:12000]}
"""

    try:
        provider = get_ai_provider()
        data = provider.generate_json(prompt)
        _mark(meta, provider.name)
    except GeminiNotConfiguredError as exc:
        if _use_local_fallback():
            _fell_back(meta, exc, 'Quiz')
            return fallback.generate_quiz_fallback_multi(sources, user, question_count, tag)
        raise
    except (GeminiQuotaError, GeminiGenerationError) as exc:
        if _use_local_fallback() and (isinstance(exc, GeminiQuotaError) or is_quota_error(exc)):
            _fell_back(meta, exc, 'Quiz')
            return fallback.generate_quiz_fallback_multi(sources, user, question_count, tag)
        if isinstance(exc, GeminiQuotaError):
            raise
        raise GeminiGenerationError(f'Quiz generation failed: {exc}') from exc
    except Exception as exc:
        if _use_local_fallback():
            _fell_back(meta, exc, 'Quiz')
            return fallback.generate_quiz_fallback_multi(sources, user, question_count, tag)
        raise GeminiGenerationError(f'Content generation failed: {exc}') from exc

    questions_data = data.get('questions') or []
    if not questions_data:
        raise GeminiGenerationError('No quiz questions were generated.')

    default_title = f'Quiz: {label}' if len(sources) == 1 else f'Quiz: {len(sources)} sources'
    quiz = Quiz.objects.create(
        user=user,
        title=(data.get('title') or default_title)[:255],
        description=(data.get('description') or f'Generated from {label}')[:2000],
        time_limit=0,
        is_public=False,
        is_published=True,
    )

    tag_note = f' [{tag}]'
    quiz.description = (quiz.description or '') + tag_note
    quiz.save(update_fields=['description'])

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
