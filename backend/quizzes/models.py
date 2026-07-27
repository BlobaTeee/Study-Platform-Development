from django.db import models
from django.contrib.auth.models import User
from materials.models import Topic

class Quiz(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quizzes')
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, related_name='quizzes')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    time_limit = models.IntegerField(default=0)
    is_public = models.BooleanField(default=False)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['topic', '-created_at']),
        ]


class Question(models.Model):
    QUESTION_TYPES = [
        ('multiple_choice', 'Multiple Choice'),
        ('true_false', 'True/False'),
        ('short_answer', 'Short Answer'),
    ]

    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES)
    options = models.JSONField(default=list)
    correct_answer = models.CharField(max_length=500)
    explanation = models.TextField(blank=True, null=True)
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.question_text[:100]

    class Meta:
        ordering = ['order', 'created_at']


class QuizAttempt(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quiz_attempts')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)
    total_points = models.IntegerField(default=0)
    is_completed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.username} - {self.quiz.title}"

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['user', '-started_at']),
            models.Index(fields=['quiz', '-started_at']),
        ]


class Answer(models.Model):
    quiz_attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    user_answer = models.TextField()
    is_correct = models.BooleanField(default=False)
    points_earned = models.IntegerField(default=0)
    answered_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.quiz_attempt.user.username} - Question {self.question.id}"

    class Meta:
        ordering = ['question__order', 'answered_at']


class MockTest(models.Model):
    """One sitting of a timed paper drawn from across a notebook.

    Separate from QuizAttempt, which is tied to a single Quiz by a non-null FK:
    a mock test deliberately spans every quiz in a notebook, so it needs its own
    record rather than a widened attempt.
    """
    # Explicit BigAutoField: every sibling table in this app was created as
    # BigAutoField in 0001_initial. Without this, apps.py's lack of
    # DEFAULT_AUTO_FIELD silently downgrades new models to 32-bit AutoField.
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mock_tests')
    # String reference on purpose: notebooks already imports quizzes.serializers,
    # so importing notebooks here would close a circular import.
    notebook = models.ForeignKey('notebooks.Notebook', on_delete=models.CASCADE,
                                 related_name='mock_tests')
    question_count = models.PositiveSmallIntegerField(default=20)
    duration_minutes = models.PositiveSmallIntegerField(default=30)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [models.Index(fields=['user', '-started_at'])]

    def __str__(self):
        return f'{self.user.username} — {self.notebook_id} ({self.question_count}q)'

    @property
    def deadline(self):
        """When the paper stops accepting answers."""
        from datetime import timedelta
        return self.started_at + timedelta(minutes=self.duration_minutes)


class MockTestQuestion(models.Model):
    """The frozen paper, and the answer given to each question.

    Freezing matters: without stored rows a refresh would resample and hand the
    student a different paper mid-sitting.
    """
    # Explicit BigAutoField: this table grows with sittings x questions, and
    # every sibling table in this app is BigAutoField (set in 0001_initial).
    id = models.BigAutoField(primary_key=True)
    mock_test = models.ForeignKey(MockTest, on_delete=models.CASCADE, related_name='paper')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    order = models.PositiveSmallIntegerField()
    user_answer = models.TextField(blank=True, default='')
    # Null until submission — grading happens once, at the end.
    is_correct = models.BooleanField(null=True, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['order']
        unique_together = [('mock_test', 'order'), ('mock_test', 'question')]
        indexes = [models.Index(fields=['mock_test', 'order'])]

    def __str__(self):
        return f'{self.mock_test_id} #{self.order}'


class PlannedTest(models.Model):
    """A test the student intends to sit, and the state of its reminder."""
    REMINDER_CHOICES = [
        (1, '1 hour before'),
        (24, '1 day before'),
        (72, '3 days before'),
    ]

    # Explicit BigAutoField: every sibling table in this app was created as
    # BigAutoField in 0001_initial; apps.py sets no DEFAULT_AUTO_FIELD.
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='planned_tests')
    notebook = models.ForeignKey('notebooks.Notebook', on_delete=models.CASCADE,
                                 related_name='planned_tests')
    scheduled_for = models.DateTimeField()
    question_count = models.PositiveSmallIntegerField(default=20)
    duration_minutes = models.PositiveSmallIntegerField(default=30)
    # `choices` only constrains the admin UI and DRF's browsable form, not the
    # database or bulk creates/shell/scripts that skip serializer validation.
    # The CheckConstraint below is what actually keeps this to {1, 24, 72} so
    # the reminder command never has to act on a bogus lead time.
    reminder_lead_hours = models.PositiveSmallIntegerField(
        default=24, choices=REMINDER_CHOICES,
        help_text='How far ahead of the test the reminder goes out.')
    # Null until sent. This is the idempotency guard: the command stamps it
    # immediately, so a scheduler firing every few minutes cannot send twice.
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    mock_test = models.OneToOneField(MockTest, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='plan')
    # Stamped when this plan is turned into a sitting. Unlike mock_test (which
    # is SET_NULL and reverts to NULL if the sitting is later deleted), this
    # stays set permanently, so "this plan was fulfilled" can't be forgotten
    # and the reminder command can't resurrect a reminder for a test already
    # taken.
    sat_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['scheduled_for']
        indexes = [
            # The reminder command's only query: unsent plans, by when they are due.
            models.Index(fields=['reminder_sent_at', 'scheduled_for']),
            models.Index(fields=['user', 'scheduled_for']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(reminder_lead_hours__in=[1, 24, 72]),
                name='planned_test_reminder_lead_choices',
            ),
        ]

    def __str__(self):
        return f'{self.user.username} — {self.scheduled_for:%Y-%m-%d %H:%M}'
