from django.urls import path

from . import views

urlpatterns = [
    path('rooms/', views.RoomsView.as_view(), name='live-rooms'),
    path('rooms/<int:pk>/', views.RoomView.as_view(), name='live-room'),
    *[path(f'rooms/<int:pk>/{name}/', views.RoomActionView.as_view(action=name), name=f'live-{name}')
      for name in ('join', 'start', 'answer', 'reveal', 'next', 'leave')],
]
