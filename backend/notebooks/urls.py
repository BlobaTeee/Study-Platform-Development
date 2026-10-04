from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ChatGroupMembersView, ChatGroupMessagesView, ChatGroupsView, ChatMessageView,
    ChatOverviewView, DirectThreadView, InviteAcceptView, NotebookViewSet, SourceViewSet,
)

router = DefaultRouter()
router.register(r'notebooks', NotebookViewSet, basename='notebook')
router.register(r'sources', SourceViewSet, basename='source')

urlpatterns = [
    path('invites/accept/', InviteAcceptView.as_view(), name='invite-accept'),
    path('messages/<int:message_id>/', ChatMessageView.as_view(), name='chat-message'),
    path('chat/groups/', ChatGroupsView.as_view(), name='chat-groups'),
    path('chat/groups/<int:group_id>/messages/', ChatGroupMessagesView.as_view(), name='chat-group-messages'),
    path('chat/groups/<int:group_id>/members/', ChatGroupMembersView.as_view(), name='chat-group-members'),
    path('chat/groups/<int:group_id>/members/<int:user_id>/', ChatGroupMembersView.as_view(), name='chat-group-member'),
    path('chat/overview/', ChatOverviewView.as_view(), name='chat-overview'),
    path('chat/direct/<int:user_id>/', DirectThreadView.as_view(), name='chat-direct'),
    path('', include(router.urls)),
]
