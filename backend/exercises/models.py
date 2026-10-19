"""Practice problems: applying what a document teaches to a case it does not
spell out, solved in steps and graded against a rubric written with the
problem."""
from django.contrib.auth.models import User
from django.db import models

from notebooks.models import Notebook, Source


class Exercise(models.Model):
    ORIGINS = [('document', 'From a document'), ('own', "The student's own")]
    STATUSES = [('new', 'New'), ('mastered', 'Mastered'), ('revisit', 'Revisit')]
    DIFFICULTIES = [('easy', 'Easy'), ('medium', 'Medium'), ('hard', 'Hard')]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exercises')
    # None for the student's own problems: they are graded from general
    # knowledge, so no notebook's documents have anything to do with them.
    notebook = models.ForeignKey(Notebook, on_delete=models.CASCADE, null=True, blank=True, related_name='exercises')
    source = models.ForeignKey(Source, on_delete=models.SET_NULL, null=True, blank=True, related_name='exercises')
    origin = models.CharField(max_length=10, choices=ORIGINS, default='document')
    prompt = models.TextField()
    difficulty = models.CharField(max_length=10, choices=DIFFICULTIES, default='medium')
    # The hidden rubric: {"solution": [str], "checkpoints": [{"id", "text", "basis"}],
    # "mistakes": [{"text", "type"}]}. Never sent to the page until the
    # problem is solved or the solution is unlocked.
    reference = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=STATUSES, default='new')
    revisit_on = models.DateField(null=True, blank=True)
    # Attempts from this moment count for the current go at the problem; a
    # revisit starts a new round so the solution is hidden again.
    round_started_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        return self.prompt[:60]


class ExerciseAttempt(models.Model):
    KINDS = [('submit', 'Submit'), ('hint', 'Hint'), ('reveal', 'Reveal')]

    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE, related_name='attempts')
    kind = models.CharField(max_length=10, choices=KINDS)
    steps = models.JSONField(default=list)
    # submit: {"verdict", "met", "first_wrong_step", "error_type", "detail", "hint"}
    # hint: {"hint"}
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
