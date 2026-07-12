from django.contrib import admin
from .models import UserProfile

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'preferred_language', 'theme', 'created_at')
    search_fields = ('user__username', 'user__email')
    list_filter = ('theme', 'created_at')
    readonly_fields = ('created_at', 'updated_at')
