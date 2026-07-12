from rest_framework import serializers
from .models import Notebook, Source


class SourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Source
        fields = [
            'id', 'notebook', 'title', 'file', 'file_type', 'original_filename', 'page_count',
            'extracted_text', 'gemini_summary', 'status', 'error_message',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'file', 'original_filename', 'page_count', 'extracted_text',
            'gemini_summary', 'status', 'error_message', 'created_at', 'updated_at',
        ]


class SourceListSerializer(serializers.ModelSerializer):
    """Lighter payload for notebook detail lists."""
    class Meta:
        model = Source
        fields = [
            'id', 'title', 'file_type', 'original_filename', 'page_count', 'status',
            'gemini_summary', 'created_at',
        ]


class NotebookSerializer(serializers.ModelSerializer):
    sources = SourceListSerializer(many=True, read_only=True)
    source_count = serializers.SerializerMethodField()

    class Meta:
        model = Notebook
        fields = [
            'id', 'title', 'description', 'source_count', 'sources',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_source_count(self, obj):
        return obj.sources.count()


class NotebookCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notebook
        fields = ['id', 'title', 'description', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']
