from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    QuizViewSet, QuestionViewSet, QuizAttemptViewSet, MockTestViewSet,
)

router = DefaultRouter()
router.register(r'quizzes', QuizViewSet, basename='quiz')
router.register(r'questions', QuestionViewSet, basename='question')
router.register(r'attempts', QuizAttemptViewSet, basename='quiz-attempt')
router.register(r'mock-tests', MockTestViewSet, basename='mock-test')

urlpatterns = [
    path('', include(router.urls)),
]
