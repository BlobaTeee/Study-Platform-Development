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

SOURCE_TAG_PREFIX = 'source:'


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


def generate_flashcards_for_sources(sources, user, count: int = 10) -> list[Flashcard]:
    count = max(3, min(count, 20))
    source_ids = [s.id for s in sources]
    tag = combined_source_tag(source_ids)

    if _use_ml_primary():
        try:
            return _generate_flashcards_ml(sources, user, count, tag)
        except Exception as exc:
            if not _use_local_fallback():
                raise GeminiGenerationError(f'ML flashcard generation failed: {exc}') from exc

    text = _sources_text(sources)
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
        return _save_flashcards_from_json(data, user, source_ids, count)
    except GeminiNotConfiguredError:
        if _use_local_fallback():
            return fallback.generate_flashcards_fallback_multi(sources, user, count, tag)
        raise
    except (GeminiQuotaError, GeminiGenerationError) as exc:
        if _use_local_fallback() and (isinstance(exc, GeminiQuotaError) or is_quota_error(exc)):
            return fallback.generate_flashcards_fallback_multi(sources, user, count, tag)
        if isinstance(exc, GeminiQuotaError):
            raise
        raise GeminiGenerationError(f'Flashcard generation failed: {exc}') from exc
    except Exception as exc:
        if _use_local_fallback():
            return fallback.generate_flashcards_fallback_multi(sources, user, count, tag)
        raise GeminiGenerationError(f'Content generation failed: {exc}') from exc


def generate_quiz_for_sources(sources, user, question_count: int = 8) -> Quiz:
    question_count = max(4, min(question_count, 15))
    source_ids = [s.id for s in sources]
    tag = combined_source_tag(source_ids)

    if _use_ml_primary():
        try:
            return _generate_quiz_ml(sources, user, question_count, tag)
        except Exception as exc:
            if not _use_local_fallback():
                raise GeminiGenerationError(f'ML quiz generation failed: {exc}') from exc

    text = _sources_text(sources)
    label = _titles_label(sources)
    doc_note = 'multiple documents' if len(sources) > 1 else 'this document'

    prompt = f"""Create a quiz with {question_count} questions from {doc_note}.
Draw from all documents; include cross-document questions when useful.

Return ONLY valid JSON:
{{"title": "...", "description": "...", "questions": [{{"question_text": "...", "question_type": "multiple_choice|true_false", "options": ["..."], "correct_answer": "...", "explanation": "..."}}]}}

Sources: {label}
Text:
{text[:12000]}
"""

    try:
        provider = get_ai_provider()
        data = provider.generate_json(prompt)
    except GeminiNotConfiguredError:
        if _use_local_fallback():
            return fallback.generate_quiz_fallback_multi(sources, user, question_count, tag)
        raise
    except (GeminiQuotaError, GeminiGenerationError) as exc:
        if _use_local_fallback() and (isinstance(exc, GeminiQuotaError) or is_quota_error(exc)):
            return fallback.generate_quiz_fallback_multi(sources, user, question_count, tag)
        if isinstance(exc, GeminiQuotaError):
            raise
        raise GeminiGenerationError(f'Quiz generation failed: {exc}') from exc
    except Exception as exc:
        if _use_local_fallback():
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

    order = 0
    for q in questions_data[:question_count]:
        qtext = (q.get('question_text') or '').strip()
        qtype = (q.get('question_type') or 'multiple_choice').strip()
        options = q.get('options') or []
        correct = (q.get('correct_answer') or '').strip()
        explanation = (q.get('explanation') or '').strip()

        if not qtext or not correct:
            continue
        if qtype not in ('multiple_choice', 'true_false', 'short_answer'):
            qtype = 'multiple_choice'
        if qtype == 'true_false' and not options:
            options = ['True', 'False']
        if qtype == 'multiple_choice' and len(options) < 2:
            continue

        Question.objects.create(
            quiz=quiz,
            question_text=qtext,
            question_type=qtype,
            options=options if isinstance(options, list) else [],
            correct_answer=correct,
            explanation=explanation or None,
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
