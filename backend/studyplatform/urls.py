"""
URL configuration for studyplatform project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include


def api_root(request):
    return JsonResponse({
        'message': 'StudyFlow API',
        'endpoints': {
            'profile': '/api/users/profiles/me/',
            'notebooks': '/api/notebooks/notebooks/',
            'upload_pdf': '/api/notebooks/notebooks/{id}/upload_pdf/',
            'admin': '/admin/',
        },
    })


urlpatterns = [
    path('', api_root),
    path('api/', api_root),
    path('admin/', admin.site.urls),
    path('api/users/', include('users.urls')),
    path('api/materials/', include('materials.urls')),
    path('api/flashcards/', include('flashcards.urls')),
    path('api/quizzes/', include('quizzes.urls')),
    path('api/analytics/', include('analytics.urls')),
    path('api/notebooks/', include('notebooks.urls')),
    path('api/study/', include('study_sessions.urls')),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
