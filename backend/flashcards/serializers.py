from rest_framework import serializers
from .models import Flashcard
from .services.card_format import BLANK


class FlashcardSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source='topic.name', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    # Read-only: provenance is set by generation. A writable list would let a
    # client claim a card belongs to a document it never saw.
    source_ids = serializers.PrimaryKeyRelatedField(
        source='sources', many=True, read_only=True)

    class Meta:
        model = Flashcard
        fields = ['id', 'user', 'username', 'topic', 'topic_name', 'question', 'answer',
                  'explanation', 'kind',
                  'difficulty', 'is_public', 'source_ids', 'views_count',
                  'correct_count', 'incorrect_count', 'created_at', 'updated_at']
        read_only_fields = ['user', 'views_count', 'correct_count', 'incorrect_count', 'created_at', 'updated_at']

    def validate(self, attrs):
        # An edit that loses the blank leaves a cloze card with nothing to fill in.
        kind = attrs.get('kind', getattr(self.instance, 'kind', 'basic'))
        question = attrs.get('question', getattr(self.instance, 'question', ''))
        if kind == 'cloze' and question.count(BLANK) != 1:
            raise serializers.ValidationError(
                {'question': f'A fill-in-the-blank card needs exactly one blank, written {BLANK}.'})
        return attrs

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)
