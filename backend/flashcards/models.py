from django.db import models
from django.contrib.auth.models import User
from materials.models import Topic

class Flashcard(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flashcards')
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, related_name='flashcards')
    question = models.TextField()
    answer = models.TextField()
    difficulty = models.CharField(max_length=20, default='medium', choices=[('easy', 'Easy'), ('medium', 'Medium'), ('hard', 'Hard')])
    is_public = models.BooleanField(default=False)
    tags = models.CharField(max_length=500, blank=True, null=True)
    views_count = models.IntegerField(default=0)
    correct_count = models.IntegerField(default=0)
    incorrect_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.question[:100]

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['topic', '-created_at']),
        ]
