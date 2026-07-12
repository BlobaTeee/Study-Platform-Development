from django.contrib import admin
from .models import StudySession

@admin.register(StudySession)
class StudySessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'started_at', 'ended_at', 'duration_minutes', 'mood_before', 'mood_after')
    search_fields = ('user__username', 'material_studied')
    list_filter = ('mood_before', 'mood_after', 'started_at')
    readonly_fields = ('started_at',)
