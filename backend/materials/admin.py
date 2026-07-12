from django.contrib import admin
from .models import Topic, StudyMaterial

@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name', 'description')
    list_filter = ('created_at',)

@admin.register(StudyMaterial)
class StudyMaterialAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'topic', 'material_type', 'is_public', 'created_at')
    search_fields = ('title', 'user__username', 'topic__name')
    list_filter = ('material_type', 'is_public', 'created_at')
    readonly_fields = ('created_at', 'updated_at')
