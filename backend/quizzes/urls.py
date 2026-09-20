from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    QuizViewSet, QuestionViewSet, QuizAttemptViewSet, MockTestViewSet,
    PlannedTestViewSet, MistakeBankView,
)

router = DefaultRouter()
router.register(r'quizzes', QuizViewSet, basename='quiz')
router.register(r'questions', QuestionViewSet, basename='question')
router.register(r'attempts', QuizAttemptViewSet, basename='quiz-attempt')
router.register(r'mock-tests', MockTestViewSet, basename='mock-test')
router.register(r'planned-tests', PlannedTestViewSet, basename='planned-test')

urlpatterns = [
    path('mistakes/', MistakeBankView.as_view(), name='mistake-bank'),
    path('', include(router.urls)),
]
