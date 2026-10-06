import logging
import re

from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext as _
from ml_pipeline.language import detect_language, language_name
from flashcards.models import Flashcard
from flashcards.services.card_format import ANSWER_RULES, CLOZE_RULES, checked_cloze
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
from .provenance import excerpt_of, source_of
from .deck_limits import batch_size

logger = logging.getLogger(__name__)

# Values reported back as `generated_by`, so a silent fallback is visible.
BY_EXTRACTIVE_ML = 'extractive-ml'
BY_EXTRACTIVE_FALLBACK = 'extractive-fallback'


def _needs_provider(lang: str) -> bool:
    """The extractive pipeline is spaCy's English model; on Vietnamese text
    it produces cloze cards around the wrong words. Rather than hand those
    over, a Vietnamese source is generated only by a provider."""
    return lang == 'vi'


def _provider_required_error(exc) -> GeminiGenerationError:
    return GeminiGenerationError(
        _('This document is in Vietnamese, so it needs Gemini or Ollama. The offline '
          'generator only handles English. Check the AI settings and try again.'))


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


def _document_chunks(sources) -> list[str]:
    """The most informative excerpts across the selected documents.

    Generating from one 12k-char prompt truncated long documents and made small
    local models lose the plot; a few focused excerpts cover the material with
    prompts a 3B model handles reliably. Each document is chunked on its own,
    so no excerpt straddles two of them: the model never sees a passage that
    changes subject mid-way, and every question can be traced to one source.
    """
    from ml_pipeline.services.chunking import chunk_text, select_chunks
    k = getattr(settings, 'RAG_CHUNKS', 3)
    chunks = []
    for source in sources:
        chunks.extend(chunk_text(source.extracted_text[:18000]))
    return select_chunks(chunks, k=k) or [_sources_text(sources)[:12000]]


def _chunk_results(provider, chunks, per_chunk, build_prompt):
    """Ask the provider about every excerpt, newest answer never jumping the queue.

    One excerpt is one model call of several seconds, and they used to run one
    after another: three excerpts meant three waits. They are independent, so
    they run together — but the results are returned in *excerpt* order, not in
    the order they happen to come back, because question order and provenance
    must not depend on which call the network finished first.

    Concurrency is capped: firing every excerpt at once is the quickest way to
    collect a rate-limit error from the provider.
    """
    if len(chunks) < 2:
        return [_one_chunk(provider, chunk, per_chunk, build_prompt) for chunk in chunks]

    from concurrent.futures import ThreadPoolExecutor
    workers = min(len(chunks), max(1, getattr(settings, 'GENERATE_CONCURRENCY', 3)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one_chunk, provider, chunk, per_chunk, build_prompt)
                   for chunk in chunks]
        return [f.result() for f in futures]


def _one_chunk(provider, chunk, per_chunk, build_prompt):
    """(data, error) for one excerpt — raising here would lose the others."""
    try:
        return provider.generate_json(build_prompt(chunk, per_chunk)), None
    except Exception as exc:
        logger.warning('Excerpt generation failed (continuing): %s', exc)
        return None, exc


def _generate_over_chunks(provider, chunks, per_chunk, build_prompt, key, limit):
    """Call the provider once per excerpt, aggregating deduped items.

    A failing excerpt is skipped rather than sinking the whole request; only if
    every excerpt fails do we raise, letting the caller fall back.
    """
    items, seen, errors = [], set(), []
    for chunk, (data, error) in zip(chunks, _chunk_results(
            provider, chunks, per_chunk, build_prompt)):
        if error is not None:
            errors.append(error)
            continue
        for item in (data.get(key) or []):
            dedup = (item.get('question') or item.get('question_text') or '').strip().lower()
            if not dedup or dedup in seen:
                continue
            seen.add(dedup)
            item['_excerpt'] = chunk   # provenance: the passage this came from
            items.append(item)
    # Every excerpt is asked, since per_chunk is sized so they are all needed to
    # reach the count; a model that over-delivers just has its extras trimmed.
    if not items and errors:
        raise errors[0]
    return items[:limit]


def _use_local_fallback() -> bool:
    return getattr(settings, 'USE_LOCAL_FALLBACK_ON_QUOTA', True)


def _use_ml_primary() -> bool:
    return getattr(settings, 'USE_ML_PRIMARY', False)


_DOC_HEADER = re.compile(r'^### Document: .*$', re.M)


def _without_document_headers(passage: str) -> str:
    """A chunk may carry the "### Document: <title>" line `_sources_text`
    inserts between documents; it is not in any source's text, and not
    something to reread."""
    return _DOC_HEADER.sub('', passage).strip()


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
        explanation = str(item.get('explanation') or '').strip()
        difficulty = (item.get('difficulty') or 'medium').lower()
        if difficulty not in ('easy', 'medium', 'hard'):
            difficulty = 'medium'
        if not question or not answer:
            continue
        kind = 'cloze' if str(item.get('kind') or '').strip().lower() == 'cloze' else 'basic'
        if kind == 'cloze':
            # A puzzle with no single answer would be graded on luck.
            question = checked_cloze(question, answer)
            if question is None:
                continue
        card = Flashcard.objects.create(
            kind=kind,
            user=user,
            question=question,
            answer=answer,
            explanation=explanation,
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
    lang = detect_language(text)

    if _use_ml_primary() and not _needs_provider(lang):
        try:
            cards = _generate_flashcards_ml(sources, user, count)
            _mark(meta, BY_EXTRACTIVE_ML)
            return cards
        except Exception as exc:
            if not _use_local_fallback():
                raise GeminiGenerationError(f'ML flashcard generation failed: {exc}') from exc

    label = _titles_label(sources)
    chunks = _document_chunks(sources)
    per_chunk = -(-count // len(chunks))  # ceil, so the excerpts cover `count`

    def build_prompt(chunk: str, n: int) -> str:
        return f"""Create exactly {n} study flashcards from this excerpt.
Write in {language_name(lang)}, the language of the excerpt.
Each flashcard must be answerable from the excerpt alone.
Ask about concepts, definitions, mechanisms, reasons and relationships — the
things a student must understand. Do not ask about incidental figures (page
counts, sample sizes, dates of publication) unless the number is itself the
point of the passage.

{ANSWER_RULES}

{CLOZE_RULES}

Return ONLY valid JSON:
{{"flashcards": [{{"kind": "basic|cloze", "question": "...", "answer": "...", "explanation": "...", "difficulty": "easy|medium|hard"}}]}}

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
            if _needs_provider(lang):
                raise _provider_required_error(exc) from exc
            _fell_back(meta, exc, 'Flashcard')
            return fallback.generate_flashcards_fallback_multi(sources, user, count)
        raise
    except (GeminiQuotaError, GeminiGenerationError) as exc:
        if _use_local_fallback() and (isinstance(exc, GeminiQuotaError) or is_quota_error(exc)):
            if _needs_provider(lang):
                raise _provider_required_error(exc) from exc
            _fell_back(meta, exc, 'Flashcard')
            return fallback.generate_flashcards_fallback_multi(sources, user, count)
        if isinstance(exc, GeminiQuotaError):
            raise
        raise GeminiGenerationError(f'Flashcard generation failed: {exc}') from exc
    except Exception as exc:
        if _use_local_fallback():
            if _needs_provider(lang):
                raise _provider_required_error(exc) from exc
            _fell_back(meta, exc, 'Flashcard')
            return fallback.generate_flashcards_fallback_multi(sources, user, count)
        raise GeminiGenerationError(f'Content generation failed: {exc}') from exc


def retire_previous_quizzes(quiz: Quiz, user, source_ids: list[int]) -> None:
    """Unpublish every other quiz of exactly this selection.

    Regenerating used to append: each press stacked another quiz on the same
    sources, and the mock-test pool drew near-duplicate — sometimes
    contradicting — questions from all of them. Retired quizzes are hidden
    from the quiz list and the pool but kept, with their attempts, because
    the answers on them are still evidence of what the student knows.
    """
    Through = Quiz.sources.through
    previous = items_with_exact_sources(
        Through.objects
        .filter(quiz__user=user, quiz__is_published=True)
        .exclude(quiz_id=quiz.id)
        .values_list('quiz_id', 'source_id'),
        source_ids)
    Quiz.objects.filter(id__in=previous).update(is_published=False)


def generate_quiz_for_sources(sources, user, question_count: int = 8,
                              meta: dict | None = None) -> Quiz:
    """Generate a quiz for this selection, replacing the one it already has.

    Pass `meta` to learn which generator was used.
    """
    quiz = _generate_quiz(sources, user, question_count, meta)
    retire_previous_quizzes(quiz, user, [s.id for s in sources])
    return quiz


def quiz_prompt(chunk: str, n: int, lang: str, label: str) -> str:
    """The question-generation prompt, at module level so it can be measured.

    `ml_pipeline/notebooks/06_question_quality.ipynb` scores what this prompt
    produces; importing it there keeps the scorecard about the real app rather
    than about a copy that drifts.
    """
    return f"""Create exactly {n} multiple-choice questions from this excerpt.
Write in {language_name(lang)}, the language of the excerpt.
For each question give: the question, the single correct answer, and exactly 3
plausible but incorrect answers (distractors) on the same topic. Do NOT put the
correct answer in the distractors, and make the distractors distinct.
Each distractor must be clearly wrong according to the excerpt — never a
synonym, a near-synonym, or a partial restatement of the correct answer.
Write answers and distractors as plain text: no "A)", "B." or similar prefixes.
Each question must be answerable from the excerpt alone.

Return ONLY valid JSON in exactly this shape:
{{"questions": [{{"question_text": "...", "correct_answer": "...", "distractors": ["...", "...", "..."], "explanation": "..."}}]}}

Source: {label}
Excerpt:
{chunk}
"""


def _quality_margin(count: int) -> int:
    """Extra questions to ask for: about a quarter, at least one.

    Measured on Gemini, one or two questions in fifteen came back with a
    distractor that is also true. A quarter more covers that without a second
    round of calls; the cost is a little more output, not more waiting.
    """
    return max(1, -(-count // 4))


def _best_first(items: list[dict]) -> list[dict]:
    """Sound questions first, flawed ones last; nothing dropped.

    Scored against the passage each question came from. Cheap — tens of
    milliseconds a question, no model call — and the same check the quality
    notebook reports with, so what it measures is what students get.
    """
    from ml_pipeline.question_quality import rank_by_quality
    ranked = rank_by_quality(items)
    if ranked != items:
        logger.info('Quality check moved flawed questions behind sound ones (%d generated)',
                    len(items))
    return ranked


def _generate_quiz(sources, user, question_count: int, meta: dict | None) -> Quiz:
    """Run the provider cascade. Creates the quiz; does not retire anything."""
    question_count = max(4, min(question_count, 15))
    source_ids = [s.id for s in sources]

    # Validate + guard against thin sources up front, for every provider, so the
    # user gets one clear message instead of empty output or a silent fallback.
    text = _sources_text(sources)
    from ml_pipeline.source_guard import check_source_text, MIN_WORDS_QUIZ
    check_source_text(text, kind='quiz', min_words=MIN_WORDS_QUIZ)
    lang = detect_language(text)

    if _use_ml_primary() and not _needs_provider(lang):
        try:
            quiz = _generate_quiz_ml(sources, user, question_count)
            _mark(meta, BY_EXTRACTIVE_ML)
            return quiz
        except Exception as exc:
            if not _use_local_fallback():
                raise GeminiGenerationError(f'ML quiz generation failed: {exc}') from exc

    label = _titles_label(sources)
    chunks = _document_chunks(sources)
    # A few more than the quiz needs, so a flawed question can be left out
    # without the quiz coming up short (see the ranking before saving).
    asked = question_count + _quality_margin(question_count)
    per_chunk = -(-asked // len(chunks))  # ceil, so excerpts cover the count

    def build_prompt(chunk: str, n: int) -> str:
        return quiz_prompt(chunk, n, lang, label)

    try:
        provider = get_ai_provider()
        questions_data = _generate_over_chunks(
            provider, chunks, per_chunk, build_prompt, 'questions', asked)
        questions_data = _best_first(questions_data)
        _mark(meta, provider.name)
    except GeminiNotConfiguredError as exc:
        if _use_local_fallback():
            if _needs_provider(lang):
                raise _provider_required_error(exc) from exc
            _fell_back(meta, exc, 'Quiz')
            return fallback.generate_quiz_fallback_multi(sources, user, question_count)
        raise
    except (GeminiQuotaError, GeminiGenerationError) as exc:
        if _use_local_fallback() and (isinstance(exc, GeminiQuotaError) or is_quota_error(exc)):
            if _needs_provider(lang):
                raise _provider_required_error(exc) from exc
            _fell_back(meta, exc, 'Quiz')
            return fallback.generate_quiz_fallback_multi(sources, user, question_count)
        if isinstance(exc, GeminiQuotaError):
            raise
        raise GeminiGenerationError(f'Quiz generation failed: {exc}') from exc
    except Exception as exc:
        if _use_local_fallback():
            if _needs_provider(lang):
                raise _provider_required_error(exc) from exc
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
    source_texts = [(s.id, s.extracted_text) for s in sources]

    order = 0
    for q in questions_data:
        if order >= question_count:
            break
        shaped = shape_quiz_question(q, rng)
        if shaped is None:
            continue  # unanswerable (no question/answer/distractor) -> skip

        # The chunk the model saw is what the student should reread; the one
        # source containing it is where. A chunk cut across two documents
        # keeps its passage but names no source.
        passage = _without_document_headers(q.get('_excerpt') or '')
        Question.objects.create(
            quiz=quiz,
            question_text=shaped['question_text'],
            question_type=shaped['question_type'],
            options=shaped['options'],
            correct_answer=shaped['correct_answer'],
            explanation=shaped['explanation'],
            order=order,
            source_id=source_of(passage, source_texts),
            source_excerpt=excerpt_of(passage),
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
