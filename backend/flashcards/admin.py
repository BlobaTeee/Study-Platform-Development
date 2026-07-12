from django.contrib import admin
from .models import Flashcard

@admin.register(Flashcard)
class FlashcardAdmin(admin.ModelAdmin):
    list_display = ('question', 'user', 'topic', 'difficulty', 'is_public', 'created_at')
    search_fields = ('question', 'answer', 'user__username', 'topic__name')
    list_filter = ('difficulty', 'is_public', 'created_at')
    readonly_fields = ('created_at', 'updated_at', 'views_count', 'correct_count', 'incorrect_count')
