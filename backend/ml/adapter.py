"""Django adapter for the ml_pipeline package."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flashcards.models import Flashcard  # noqa: E402
from quizzes.models import Quiz, Question  # noqa: E402


def _combined_text(sources) -> str:
    return "\n\n".join(s.extracted_text for s in sources if s.extracted_text)


def _label(sources) -> str:
    if len(sources) == 1:
        return sources[0].title
    return f"{len(sources)} documents"


def generate_flashcards_ml(sources, user, count: int, tag: str) -> list[Flashcard]:
    from ml_pipeline.services.flashcard_generator import FlashcardGenerator

    text = _combined_text(sources)
    cards = FlashcardGenerator().generate(text, count=count, title=_label(sources))
    if not cards:
        raise ValueError("ML flashcard generator returned no cards.")

    created = []
    for item in cards[:count]:
        card = Flashcard.objects.create(
            user=user,
            question=item["question"],
            answer=item["answer"],
            difficulty=item.get("difficulty", "medium"),
            tags=tag,
            is_public=False,
        )
        created.append(card)
    return created


def generate_quiz_ml(sources, user, question_count: int, tag: str) -> Quiz:
    from ml_pipeline.services.quiz_generator import QuizGenerator

    text = _combined_text(sources)
    label = _label(sources)
    data = QuizGenerator().generate(text, question_count=question_count, title=f"Quiz: {label}")

    quiz = Quiz.objects.create(
        user=user,
        title=data["title"][:255],
        description=(data.get("description") or "") + f" [{tag}]",
        time_limit=0,
        is_public=False,
        is_published=True,
    )

    order = 0
    for q in data.get("questions", [])[:question_count]:
        Question.objects.create(
            quiz=quiz,
            question_text=q["question_text"],
            question_type=q.get("question_type", "multiple_choice"),
            options=q.get("options", []),
            correct_answer=q["correct_answer"],
            explanation=q.get("explanation"),
            order=order,
        )
        order += 1

    if order == 0:
        quiz.delete()
        raise ValueError("ML quiz generator returned no valid questions.")
    return quiz


def get_study_recommendations(user, study_text: str = "", n: int = 5) -> list[dict]:
    from flashcards.models import Flashcard
    from quizzes.models import QuizAttempt
    from ml_pipeline.services.recommendation_engine import RecommendationEngine

    flashcards = Flashcard.objects.filter(user=user)
    attempts = QuizAttempt.objects.filter(user=user, is_completed=True).select_related("quiz")
    engine = RecommendationEngine()
    profile = engine.build_performance_profile(flashcards=flashcards, quiz_attempts=attempts)
    return engine.recommend_from_text(study_text, performance_by_topic=profile, n=n)


def get_learning_path(user, subject: str | None = None, limit: int = 15) -> list[dict]:
    from flashcards.models import Flashcard
    from quizzes.models import QuizAttempt
    from ml_pipeline.services.learning_path import LearningPathEngine
    from ml_pipeline.services.recommendation_engine import RecommendationEngine

    flashcards = Flashcard.objects.filter(user=user)
    attempts = QuizAttempt.objects.filter(user=user, is_completed=True).select_related("quiz")
    engine = RecommendationEngine()
    profile = engine.build_performance_profile(flashcards=flashcards, quiz_attempts=attempts)
    path_engine = LearningPathEngine()
    mastered = path_engine.estimate_mastery_from_performance(profile)
    return path_engine.get_learning_path(subject=subject, mastered_subtopics=mastered, limit=limit)
