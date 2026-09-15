"""Local study content when Gemini quota is unavailable.

Uses ML pipeline (spaCy + scikit-learn) when available, with simple
chunk-based generation as a last resort.
"""
import re
from flashcards.models import Flashcard
from quizzes.models import Quiz, Question


def _chunks(text: str, min_len: int = 80) -> list[str]:
    parts = re.split(r'\n\s*\n+', text)
    chunks = []
    for part in parts:
        part = re.sub(r'\s+', ' ', part).strip()
        if len(part) >= min_len:
            chunks.append(part[:1200])
    if not chunks:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = [s.strip() for s in sentences if len(s.strip()) >= min_len]
    return chunks


def _combined_text(sources) -> str:
    return '\n\n'.join(s.extracted_text for s in sources if s.extracted_text)


def generate_flashcards_fallback(source, user, count: int) -> list[Flashcard]:
    chunks = _chunks(source.extracted_text)
    if not chunks:
        raise ValueError('Not enough text to build flashcards without AI.')

    created = []
    for i, chunk in enumerate(chunks[:count]):
        card = Flashcard.objects.create(
            user=user,
            question=f'What are the main points in section {i + 1} of "{source.title}"?',
            answer=chunk[:800],
            difficulty='medium',
            is_public=False,
        )
        created.append(card)
    return created


def generate_flashcards_fallback_multi(sources, user, count: int) -> list[Flashcard]:
    try:
        from ml.adapter import generate_flashcards_ml
        return generate_flashcards_ml(sources, user, count)
    except Exception:
        pass

    class _Combined:
        def __init__(self, title, text):
            self.title = title
            self.extracted_text = text

    label = sources[0].title if len(sources) == 1 else f'{len(sources)} documents'
    combined = _Combined(label, _combined_text(sources))
    return generate_flashcards_fallback(combined, user, count)


def generate_quiz_fallback_multi(sources, user, question_count: int) -> Quiz:
    try:
        from ml.adapter import generate_quiz_ml
        return generate_quiz_ml(sources, user, question_count)
    except Exception:
        pass

    class _Combined:
        def __init__(self, title, text):
            self.title = title
            self.extracted_text = text

    label = sources[0].title if len(sources) == 1 else f'{len(sources)} documents'
    combined = _Combined(label, _combined_text(sources))
    quiz = generate_quiz_fallback(combined, user, question_count)
    # The stand-in has no id; the quiz is linked to the documents it stood for.
    quiz.sources.set([s.id for s in sources])
    return quiz


def generate_quiz_fallback(source, user, question_count: int) -> Quiz:
    chunks = _chunks(source.extracted_text)
    if len(chunks) < 2:
        raise ValueError('Not enough text to build a quiz without AI.')

    quiz = Quiz.objects.create(
        user=user,
        title=f'Quiz: {source.title}'[:255],
        description='Basic quiz from document sections',
        time_limit=0,
        is_public=False,
        is_published=True,
    )

    order = 0
    for i, chunk in enumerate(chunks[:question_count]):
        statement = chunk[:200] + ('…' if len(chunk) > 200 else '')
        Question.objects.create(
            quiz=quiz,
            question_text=f'True or False: This statement reflects the material — "{statement}"',
            question_type='true_false',
            options=['True', 'False'],
            correct_answer='True',
            explanation='Review the corresponding section in your PDF source.',
            order=order,
        )
        order += 1

    if order == 0:
        quiz.delete()
        raise ValueError('Could not create quiz questions.')
    return quiz
