from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AnalyticsViewSet

router = DefaultRouter()
# Kept at 'sessions' so existing client paths (/analytics/sessions/summary/)
# keep working; the manual study-session CRUD behind it was removed.
router.register(r'sessions', AnalyticsViewSet, basename='analytics')

urlpatterns = [
    path('', include(router.urls)),
]
