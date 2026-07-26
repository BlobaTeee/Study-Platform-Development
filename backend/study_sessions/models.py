from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from notebooks.models import Notebook
from flashcards.models import Flashcard
from . import scheduling


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
        """Update streak based on session date (a date or datetime)."""
        if session_date is None:
            return
        if hasattr(session_date, 'date'):
            session_date = session_date.date()
        result = scheduling.advance_streak(
            self.current_streak, self.best_streak, self.last_session_date, session_date
        )
        self.current_streak = result.current
        self.best_streak = result.best
        self.last_session_date = result.last_date
        self.save()


class CardReviewQuerySet(models.QuerySet):
    def grades(self):
        """Only rows recording an actual recall.

        Seed rows carry a schedule to a regenerated card and represent no
        answer, so counting them would inflate review totals and dilute
        accuracy. Scheduling reads the unfiltered manager on purpose — a seed
        row is exactly what tells a variant when it is next due.
        """
        return self.filter(is_seed=False)


class CardReview(models.Model):
    """Track individual flashcard performance for spaced repetition."""
    RESULT_CHOICES = [
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

    is_seed = models.BooleanField(
        default=False,
        help_text='Carries a schedule to a regenerated card; not a real recall.',
    )

    objects = CardReviewQuerySet.as_manager()

    class Meta:
        ordering = ['-review_date']
        unique_together = ('user', 'flashcard', 'review_date')

    def __str__(self):
        return f"{self.user.username} - {self.flashcard.question[:30]} ({self.result})"

    @classmethod
    def record(cls, user, flashcard, result, session=None):
        """Log one self-graded review and schedule the card's next appearance.

        The card's SM-2 state lives on its most recent review, so it is carried
        forward here; starting from the field defaults each time would pin every
        card to a one-day interval forever.
        """
        # Ordering spelled out rather than inherited from Meta: reordering
        # that default would silently carry forward a card's *oldest*
        # schedule and pin its interval forever.
        previous = (cls.objects.filter(user=user, flashcard=flashcard)
                    .order_by('-review_date').first())
        review = cls(
            user=user,
            flashcard=flashcard,
            session=session,
            result=result,
            interval=previous.interval if previous else scheduling.INITIAL.interval,
            ease_factor=previous.ease_factor if previous else scheduling.INITIAL.ease_factor,
            repetitions=previous.repetitions if previous else scheduling.INITIAL.repetitions,
        )
        review.calculate_next_review()

        # A failed card comes back as a different question on the same concept,
        # but generating one costs a model call, so only mark it here. The
        # due-fetch does the work, and only for cards actually returned to.
        if result == scheduling.HARD and not flashcard.needs_regeneration:
            flashcard.needs_regeneration = True
            flashcard.regeneration_attempts = 0
            flashcard.save(update_fields=['needs_regeneration',
                                          'regeneration_attempts'])
        elif result in scheduling.CORRECT_RESULTS and flashcard.needs_regeneration:
            # Recalling the card means it no longer needs replacing: without
            # this, a card failed once and then learned would still be swapped
            # out weeks later, discarding what the learner had just mastered.
            flashcard.needs_regeneration = False
            flashcard.regeneration_attempts = 0
            flashcard.save(update_fields=['needs_regeneration',
                                          'regeneration_attempts'])

        streak, _ = StudyStreak.objects.get_or_create(user=user)
        streak.update_streak(timezone.localdate())
        return review

    def calculate_next_review(self):
        """Apply the SM-2 step to this review and save it."""
        from datetime import timedelta as td

        self.interval, self.ease_factor, self.repetitions = scheduling.next_schedule(
            self.result,
            interval=self.interval,
            ease_factor=self.ease_factor,
            repetitions=self.repetitions,
        )
        self.next_review_date = timezone.localdate() + td(days=self.interval)
        self.save()
