from rest_framework import serializers
from .models import StudySession, StudyStreak, CardReview
from notebooks.models import Notebook


class StudySessionSerializer(serializers.ModelSerializer):
    notebook_title = serializers.CharField(source='notebook.title', read_only=True)
    actual_duration = serializers.IntegerField(read_only=True)
    card_accuracy = serializers.FloatField(read_only=True)

    class Meta:
        model = StudySession
        fields = [
            'id', 'notebook', 'notebook_title', 'session_type', 'scheduled_start',
            'actual_start', 'actual_end', 'planned_duration', 'actual_duration',
            'mood_before', 'mood_after', 'focus_level', 'cards_reviewed', 'cards_correct',
            'cards_incorrect', 'card_accuracy', 'quiz_score', 'completed', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'actual_duration', 'card_accuracy']


class StudySessionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudySession
        fields = ['notebook', 'session_type', 'scheduled_start', 'planned_duration']


class CardReviewSerializer(serializers.ModelSerializer):
    flashcard_question = serializers.CharField(source='flashcard.question', read_only=True)
    flashcard_answer = serializers.CharField(source='flashcard.answer', read_only=True)

    class Meta:
        model = CardReview
        fields = [
            'id', 'flashcard', 'flashcard_question', 'flashcard_answer', 'result',
            'interval', 'ease_factor', 'repetitions', 'next_review_date', 'review_date'
        ]
        read_only_fields = ['id', 'interval', 'ease_factor', 'repetitions', 'next_review_date', 'review_date']


class StudyStreakSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudyStreak
        fields = ['current_streak', 'best_streak', 'total_study_minutes', 'last_session_date']
        read_only_fields = ['current_streak', 'best_streak', 'total_study_minutes', 'last_session_date']
