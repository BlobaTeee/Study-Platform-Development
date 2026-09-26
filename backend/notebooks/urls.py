from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InviteAcceptView, NotebookMessageView, NotebookViewSet, SourceViewSet

router = DefaultRouter()
router.register(r'notebooks', NotebookViewSet, basename='notebook')
router.register(r'sources', SourceViewSet, basename='source')

urlpatterns = [
    path('invites/accept/', InviteAcceptView.as_view(), name='invite-accept'),
    path('messages/<int:message_id>/', NotebookMessageView.as_view(), name='notebook-message'),
    path('', include(router.urls)),
]
