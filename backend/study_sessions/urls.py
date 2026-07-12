from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import StudySessionViewSet, StudyStreakViewSet, CardReviewViewSet

router = DefaultRouter()
router.register(r'sessions', StudySessionViewSet, basename='study-session')
router.register(r'streaks', StudyStreakViewSet, basename='study-streak')
router.register(r'card-reviews', CardReviewViewSet, basename='card-review')

urlpatterns = [
    path('', include(router.urls)),
]
