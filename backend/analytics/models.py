from django.db import models
from django.contrib.auth.models import User

class StudySession(models.Model):
    user = models.ForeignKey(
    User,
    on_delete=models.CASCADE,
    related_name='analytics_study_sessions'
    )
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(default=0)
    material_studied = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    mood_before = models.CharField(max_length=20, blank=True, null=True, choices=[
        ('great', 'Great'),
        ('good', 'Good'),
        ('neutral', 'Neutral'),
        ('tired', 'Tired'),
        ('unmotivated', 'Unmotivated'),
    ])
    mood_after = models.CharField(max_length=20, blank=True, null=True, choices=[
        ('great', 'Great'),
        ('good', 'Good'),
        ('neutral', 'Neutral'),
        ('tired', 'Tired'),
        ('unmotivated', 'Unmotivated'),
    ])

    def __str__(self):
        return f"{self.user.username} - {self.started_at}"

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['user', '-started_at']),
        ]
