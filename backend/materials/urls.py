from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TopicViewSet, StudyMaterialViewSet

router = DefaultRouter()
router.register(r'topics', TopicViewSet, basename='topic')
router.register(r'materials', StudyMaterialViewSet, basename='study-material')

urlpatterns = [
    path('', include(router.urls)),
]
