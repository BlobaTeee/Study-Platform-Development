"""Guidance services for the ML pipeline (recommendations + learning path).

Note: generation services (flashcard/quiz) are a later spec and are imported
lazily by the Django adapter, so they are intentionally not re-exported here.
"""
from .learning_path import LearningPathEngine
from .recommendation_engine import RecommendationEngine

__all__ = ["RecommendationEngine", "LearningPathEngine"]
