from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from notebooks.models import Notebook
from flashcards.models import Flashcard


class StudySession(models.Model):
    SESSION_TYPE_CHOICES = [
        ('pomodoro', 'Pomodoro (25 min)'),
        ('deep_work', 'Deep Work (50 min)'),
        ('review', 'Review Session (15 min)'),
        ('custom', 'Custom Duration'),
    ]

    user = models.ForeignKey(
    User,
    on_delete=models.CASCADE,
    related_name='study_sessions'
    )
    notebook = models.ForeignKey(Notebook, on_delete=models.CASCADE, related_name='study_sessions')
    session_type = models.CharField(max_length=20, choices=SESSION_TYPE_CHOICES, default='pomodoro')

    # Timing
    scheduled_start = models.DateTimeField()
    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end = models.DateTimeField(null=True, blank=True)
    planned_duration = models.IntegerField(help_text='Duration in minutes')

    # Tracking
    mood_before = models.CharField(
        max_length=5,
        choices=[('1', '😞'), ('2', '😐'), ('3', '🙂'), ('4', '😄')],
        null=True,
        blank=True
    )
    mood_after = models.CharField(
        max_length=5,
        choices=[('1', '😞'), ('2', '😐'), ('3', '🙂'), ('4', '😄')],
        null=True,
        blank=True
    )
    focus_level = models.IntegerField(null=True, blank=True, help_text='1-10 rating')

    # Stats
    cards_reviewed = models.IntegerField(default=0)
    cards_correct = models.IntegerField(default=0)
    cards_incorrect = models.IntegerField(default=0)
    quiz_score = models.FloatField(null=True, blank=True)

    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} - {self.notebook.title} ({self.planned_duration}min)"

    @property
    def actual_duration(self):
        """Calculate actual duration in minutes."""
        if self.actual_start and self.actual_end:
            delta = self.actual_end - self.actual_start
            return int(delta.total_seconds() / 60)
        return 0

    @property
    def card_accuracy(self):
        """Calculate accuracy percentage."""
        total = self.cards_correct + self.cards_incorrect
        if total == 0:
            return 0
        return (self.cards_correct / total) * 100


class StudyStreak(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='study_streak')
    current_streak = models.IntegerField(default=0)
    best_streak = models.IntegerField(default=0)
    last_session_date = models.DateField(null=True, blank=True)
    total_study_minutes = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - Streak: {self.current_streak}"

    def update_streak(self, session_date):
        """Update streak based on session date."""
        if session_date is None:
            return

        if hasattr(session_date, 'date'):
            session_date = session_date.date()

        if self.last_session_date is None:
            # First session ever
            self.current_streak = 1
            self.best_streak = 1
        elif (session_date - self.last_session_date).days == 1:
            # Consecutive day
            self.current_streak += 1
            if self.current_streak > self.best_streak:
                self.best_streak = self.current_streak
        elif (session_date - self.last_session_date).days > 1:
            # Streak broken
            self.current_streak = 1
        # Same day doesn't change streak

        self.last_session_date = session_date
        self.save()


class CardReview(models.Model):
    """Track individual flashcard performance for spaced repetition."""
    RESULT_CHOICES = [
        ('again', 'Again (forgot)'),
        ('hard', 'Hard'),
        ('good', 'Good'),
        ('easy', 'Very Easy'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='card_reviews')
    flashcard = models.ForeignKey(Flashcard, on_delete=models.CASCADE, related_name='reviews')
    session = models.ForeignKey(StudySession, on_delete=models.CASCADE, null=True, blank=True)

    result = models.CharField(max_length=10, choices=RESULT_CHOICES)
    review_date = models.DateTimeField(auto_now_add=True)

    # Spaced repetition data
    interval = models.IntegerField(default=1, help_text='Days until next review')
    ease_factor = models.FloatField(default=2.5, help_text='SM-2 ease factor')
    repetitions = models.IntegerField(default=0)
    next_review_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-review_date']
        unique_together = ('user', 'flashcard', 'review_date')

    def __str__(self):
        return f"{self.user.username} - {self.flashcard.question[:30]} ({self.result})"

    def calculate_next_review(self):
        """SM-2 spaced repetition algorithm."""
        from datetime import timedelta as td

        self.repetitions += 1

        # SM-2 algorithm
        if self.result == 'again':
            self.repetitions = 0
            self.interval = 1
            self.ease_factor = max(1.3, self.ease_factor - 0.2)
        elif self.result == 'hard':
            self.interval = max(1, int(self.interval * 1.2))
            self.ease_factor = max(1.3, self.ease_factor - 0.15)
        elif self.result == 'good':
            if self.repetitions == 1:
                self.interval = 1
            elif self.repetitions == 2:
                self.interval = 3
            else:
                self.interval = int(self.interval * self.ease_factor)
        elif self.result == 'easy':
            self.interval = int(self.interval * self.ease_factor)
            self.ease_factor = self.ease_factor + 0.1

        self.next_review_date = timezone.now().date() + td(days=self.interval)
        self.save()
