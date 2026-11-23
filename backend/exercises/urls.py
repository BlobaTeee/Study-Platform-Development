from django.urls import path

from . import views

urlpatterns = [
    path('', views.ExerciseListView.as_view(), name='exercises'),
    path('generate/', views.GenerateView.as_view(), name='exercises-generate'),
    path('own-set/', views.OwnSetView.as_view(), name='exercises-own-set'),
    path('own/', views.OwnProblemView.as_view(), name='exercises-own'),
    path('read-photo/', views.ReadPhotoView.as_view(), name='exercises-read-photo'),
    path('mistakes/', views.MistakesView.as_view(), name='exercises-mistakes'),
    path('<int:pk>/', views.ExerciseDetailView.as_view(), name='exercise'),
    path('<int:pk>/submit/', views.SubmitView.as_view(), name='exercise-submit'),
    path('<int:pk>/hint/', views.HintView.as_view(), name='exercise-hint'),
    path('<int:pk>/reveal/', views.RevealView.as_view(), name='exercise-reveal'),
]
