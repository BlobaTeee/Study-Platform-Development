from rest_framework import serializers
from .models import Flashcard


class FlashcardSerializer(serializers.ModelSerializer):
    topic_name = serializers.CharField(source='topic.name', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = Flashcard
        fields = ['id', 'user', 'username', 'topic', 'topic_name', 'question', 'answer', 
                  'difficulty', 'is_public', 'tags', 'views_count', 'correct_count', 
                  'incorrect_count', 'created_at', 'updated_at']
        read_only_fields = ['user', 'views_count', 'correct_count', 'incorrect_count', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)
