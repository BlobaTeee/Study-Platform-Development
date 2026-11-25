from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    QuizViewSet, QuestionViewSet, QuizAttemptViewSet, MockTestViewSet,
    PlannedTestViewSet, MistakeBankView, MistakeRedoView, MistakeSummaryView, WeakConceptsView, PracticeConceptView,
    MisconceptionsView, MisconceptionPracticeView,
)

router = DefaultRouter()
router.register(r'quizzes', QuizViewSet, basename='quiz')
router.register(r'questions', QuestionViewSet, basename='question')
router.register(r'attempts', QuizAttemptViewSet, basename='quiz-attempt')
router.register(r'mock-tests', MockTestViewSet, basename='mock-test')
router.register(r'planned-tests', PlannedTestViewSet, basename='planned-test')

urlpatterns = [
    path('mistakes/', MistakeBankView.as_view(), name='mistake-bank'),
    path('mistakes/summary/', MistakeSummaryView.as_view(), name='mistake-summary'),
    path('mistakes/redo/', MistakeRedoView.as_view(), name='mistake-redo'),
    path('weak-concepts/', WeakConceptsView.as_view(), name='weak-concepts'),
    path('weak-concepts/practice/', PracticeConceptView.as_view(), name='practice-concept'),
    path('misconceptions/', MisconceptionsView.as_view(), name='misconceptions'),
    path('misconceptions/practice/', MisconceptionPracticeView.as_view(), name='misconception-practice'),
    path('', include(router.urls)),
]
