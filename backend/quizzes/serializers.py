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
    `question_text`/`options` read straight off this row (denormalised at
    freeze time onto MockTestQuestion, not looked up via `question`) so the
    sitting still renders correctly even if the source quiz was since deleted
    or regenerated — but that denormalisation is exactly why this class must
    keep listing only these four fields: `correct_answer` now lives on this
    same row too, and must stay off this serializer regardless.
    """
    class Meta:
        model = MockTestQuestion
        fields = ['id', 'order', 'question_text', 'options', 'user_answer']
        read_only_fields = fields


class MockTestQuestionReviewSerializer(serializers.ModelSerializer):
    """The same question after submission, with the marking revealed.

    Reads `correct_answer`/`explanation` off this row's own denormalised
    columns rather than following `question` — that FK can be NULL by the
    time this is rendered (its quiz deleted or regenerated long after the
    sitting), and the review must stay complete regardless.
    """
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
                  'reminder_sent_at', 'mock_test', 'sat_at', 'created_at']
        # sat_at read-only and exposed: it's how the UI tells a plan that has
        # already been turned into a sitting from one that hasn't, without
        # trusting mock_test alone (mock_test is SET_NULL and reverts to NULL
        # if that sitting is later deleted; sat_at does not).
        read_only_fields = ['reminder_sent_at', 'mock_test', 'sat_at', 'created_at']
        extra_kwargs = {
            # Same wording as validate_notebook's rejection below, on purpose
            # — see that method's comment for why the two must read alike.
            'notebook': {'error_messages': {'does_not_exist': 'Notebook not found.'}},
        }

    def validate_notebook(self, value):
        # The field's own queryset (Notebook.objects.all(), via the FK)
        # only proves the id exists *somewhere* — not that it's this user's.
        # Without this check a student could POST another user's notebook
        # id and plan a test against it (an IDOR): the notebook's title
        # would then leak back through `notebook_title` here and again in
        # the reminder email sent later. Rejecting with the exact same
        # message as "no such notebook" (rather than something like "not
        # your notebook") is deliberate: telling the two apart would let
        # this field be used to enumerate which notebook ids belong to
        # other users.
        user = self.context['request'].user
        if value.user_id != user.id:
            raise serializers.ValidationError('Notebook not found.')
        return value

    def validate_scheduled_for(self, value):
        from django.utils import timezone
        if value <= timezone.now():
            raise serializers.ValidationError('Pick a time in the future.')
        return value
