from django.contrib import admin
from .models import StudySession, StudyStreak, CardReview


@admin.register(StudySession)
class StudySessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'notebook', 'planned_duration', 'completed', 'created_at')
    list_filter = ('completed', 'session_type', 'created_at')
    search_fields = ('user__username', 'notebook__title')
    readonly_fields = ('created_at', 'updated_at', 'actual_duration', 'card_accuracy')


@admin.register(StudyStreak)
class StudyStreakAdmin(admin.ModelAdmin):
    list_display = ('user', 'current_streak', 'best_streak', 'total_study_minutes')
    search_fields = ('user__username',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(CardReview)
class CardReviewAdmin(admin.ModelAdmin):
    list_display = ('user', 'flashcard', 'result', 'interval', 'next_review_date')
    list_filter = ('result', 'review_date')
    search_fields = ('user__username', 'flashcard__question')
    readonly_fields = ('review_date',)
