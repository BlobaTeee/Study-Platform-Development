from django.contrib import admin
from .models import Notebook, Source


@admin.register(Notebook)
class NotebookAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'updated_at')
    search_fields = ('title', 'user__username')


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ('title', 'notebook', 'file_type', 'status', 'page_count', 'created_at')
    list_filter = ('status', 'file_type')
