from rest_framework import serializers
from .models import StudySession


class StudySessionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = StudySession
        fields = ['id', 'user', 'username', 'started_at', 'ended_at', 'duration_minutes', 
                  'material_studied', 'notes', 'mood_before', 'mood_after']
        read_only_fields = ['user', 'started_at']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)
