from rest_framework import serializers
from .models import (
    Quiz, Question, QuizAttempt, Answer, MockTest, MockTestQuestion, PlannedTest,
)


class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = ['id', 'quiz', 'question_text', 'question_type', 'options', 'correct_answer', 
                  'explanation', 'order', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class QuizSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)
    topic_name = serializers.CharField(source='topic.name', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = Quiz
        fields = ['id', 'user', 'username', 'topic', 'topic_name', 'title', 'description', 
                  'time_limit', 'is_public', 'is_published', 'questions', 'created_at', 'updated_at']
        read_only_fields = ['user', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class AnswerSerializer(serializers.ModelSerializer):
    question_text = serializers.CharField(source='question.question_text', read_only=True)

    class Meta:
        model = Answer
        fields = ['id', 'quiz_attempt', 'question', 'question_text', 'user_answer',
                  'is_correct', 'points_earned', 'answered_at']
        read_only_fields = ['answered_at']


class QuizAttemptSerializer(serializers.ModelSerializer):
    answers = AnswerSerializer(many=True, read_only=True)
    quiz_title = serializers.CharField(source='quiz.title', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = QuizAttempt
        fields = ['id', 'quiz', 'quiz_title', 'user', 'username', 'started_at', 'completed_at',
                  'score', 'total_points', 'is_completed', 'answers']
        read_only_fields = ['started_at', 'user']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class MockTestQuestionSerializer(serializers.ModelSerializer):
    """A question as it appears *during* the test — no answer, no marking.

    Withholding `correct_answer` and `is_correct` here is what separates a test
    from a quiz; the review serializer supplies them once the paper is handed in.
    """
    question_text = serializers.CharField(source='question.question_text', read_only=True)
    options = serializers.JSONField(source='question.options', read_only=True)

    class Meta:
        model = MockTestQuestion
        fields = ['id', 'order', 'question_text', 'options', 'user_answer']
        read_only_fields = fields


class MockTestQuestionReviewSerializer(serializers.ModelSerializer):
    """The same question after submission, with the marking revealed."""
    question_text = serializers.CharField(source='question.question_text', read_only=True)
    options = serializers.JSONField(source='question.options', read_only=True)
    correct_answer = serializers.CharField(source='question.correct_answer', read_only=True)
    explanation = serializers.CharField(source='question.explanation', read_only=True)

    class Meta:
        model = MockTestQuestion
        fields = ['id', 'order', 'question_text', 'options', 'user_answer',
                  'correct_answer', 'explanation', 'is_correct']
        read_only_fields = fields


class MockTestSerializer(serializers.ModelSerializer):
    paper = MockTestQuestionSerializer(many=True, read_only=True)
    notebook_title = serializers.CharField(source='notebook.title', read_only=True)
    deadline = serializers.DateTimeField(read_only=True)

    class Meta:
        model = MockTest
        fields = ['id', 'notebook', 'notebook_title', 'question_count',
                  'duration_minutes', 'started_at', 'deadline', 'completed_at',
                  'score', 'paper']
        read_only_fields = ['started_at', 'completed_at', 'score', 'paper']


class PlannedTestSerializer(serializers.ModelSerializer):
    notebook_title = serializers.CharField(source='notebook.title', read_only=True)

    class Meta:
        model = PlannedTest
        fields = ['id', 'notebook', 'notebook_title', 'scheduled_for',
                  'question_count', 'duration_minutes', 'reminder_lead_hours',
                  'reminder_sent_at', 'mock_test', 'created_at']
        read_only_fields = ['reminder_sent_at', 'mock_test', 'created_at']

    def validate_scheduled_for(self, value):
        from django.utils import timezone
        if value <= timezone.now():
            raise serializers.ValidationError('Pick a time in the future.')
        return value
