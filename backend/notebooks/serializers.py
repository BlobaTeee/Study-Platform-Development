from rest_framework import serializers
from .models import Notebook, Source
from .services.textnorm import clean_summary


class _CleanSummaryMixin:
    """Overviews written before the model's lead-in was stripped at ingest
    ("Here is a summary…:") are cleaned on the way out, so stored rows need
    no rewrite and every client gets the same text."""

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if 'gemini_summary' in data:
            data['gemini_summary'] = clean_summary(data['gemini_summary'])
        return data

#: Characters of document text a source detail returns. The reader only ever
#: rendered this much, so sending the rest meant shipping a 167,000-character
#: document to display 8,000 of it. Generation reads `extracted_text` straight
#: from the model server-side and is unaffected by this.
TEXT_PREVIEW_CHARS = 8000


class SourceSerializer(_CleanSummaryMixin, serializers.ModelSerializer):
    text_preview = serializers.SerializerMethodField()
    text_length = serializers.SerializerMethodField()

    class Meta:
        model = Source
        fields = [
            'id', 'notebook', 'title', 'file', 'file_type', 'original_filename', 'page_count',
            'text_preview', 'text_length', 'gemini_summary', 'key_points', 'status', 'error_message',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'file', 'original_filename', 'page_count',
            'gemini_summary', 'key_points', 'status', 'error_message', 'created_at', 'updated_at',
        ]

    def get_text_preview(self, obj) -> str:
        """The opening of the document, not the whole thing.

        Named `text_preview` rather than left as `extracted_text` on purpose: a
        truncated value under the old name would look complete to every client
        that reads it.
        """
        return (obj.extracted_text or '')[:TEXT_PREVIEW_CHARS]

    def get_text_length(self, obj) -> int:
        """Full length, so a reader can say how much it is not showing."""
        return len(obj.extracted_text or '')


class SourceListSerializer(_CleanSummaryMixin, serializers.ModelSerializer):
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
    # How many people are in it. 1 is a private notebook; more means shared,
    # which is all a cover needs to say.
    member_count = serializers.SerializerMethodField()
    # Whether the person asking owns it: only their own notebooks may receive
    # a document they move or upload.
    is_owner = serializers.SerializerMethodField()

    class Meta:
        model = Notebook
        fields = [
            'id', 'title', 'description', 'source_count', 'member_count', 'is_owner', 'sources',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_is_owner(self, obj):
        request = self.context.get('request')
        return bool(request and obj.user_id == request.user.id)

    def get_source_count(self, obj):
        return obj.sources.count()

    def get_member_count(self, obj):
        return obj.members.count()


class NotebookCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notebook
        fields = ['id', 'title', 'description', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']
