from django.contrib import admin
from .models import Quiz, Question, QuizAttempt, Answer

@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'topic', 'is_public', 'is_published', 'created_at')
    search_fields = ('title', 'user__username', 'topic__name')
    list_filter = ('is_public', 'is_published', 'created_at')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('question_text', 'quiz', 'question_type', 'order')
    search_fields = ('question_text', 'quiz__title')
    list_filter = ('question_type', 'quiz')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ('user', 'quiz', 'score', 'is_completed', 'started_at')
    search_fields = ('user__username', 'quiz__title')
    list_filter = ('is_completed', 'started_at')
    readonly_fields = ('started_at',)

@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ('quiz_attempt', 'question', 'is_correct', 'points_earned', 'answered_at')
    search_fields = ('quiz_attempt__user__username', 'question__question_text')
    list_filter = ('is_correct', 'answered_at')
