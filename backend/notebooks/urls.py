from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import NotebookViewSet, SourceViewSet

router = DefaultRouter()
router.register(r'notebooks', NotebookViewSet, basename='notebook')
router.register(r'sources', SourceViewSet, basename='source')

urlpatterns = [
    path('', include(router.urls)),
]
