"""A live round in a shared notebook: who is in it, where it has got to, and
what each player answered. The rules are in services/rounds.py."""
from django.contrib.auth.models import User
from django.db import models


class LiveSession(models.Model):
    STATUSES = [('lobby', 'Lobby'), ('question', 'Question'), ('reveal', 'Reveal'), ('finished', 'Finished')]

    notebook = models.ForeignKey('notebooks.Notebook', on_delete=models.CASCADE, related_name='live_sessions')
    host = models.ForeignKey(User, on_delete=models.CASCADE, related_name='hosted_live_sessions')
    status = models.CharField(max_length=10, choices=STATUSES, default='lobby')
    # Chosen when the room opens, so everyone gets the same questions in the same order.
    question_ids = models.JSONField(default=list)
    index = models.PositiveSmallIntegerField(default=0)
    seconds = models.PositiveSmallIntegerField(default=20)
    question_started_at = models.DateTimeField(null=True, blank=True)
    revealed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['notebook', 'status'])]


class LiveParticipant(models.Model):
    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='live_participations')
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['joined_at', 'id']
        constraints = [models.UniqueConstraint(fields=['session', 'user'], name='one_seat_per_live_session')]


class LiveAnswer(models.Model):
    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name='answers')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='live_answers')
    # Kept when the quiz goes, so a finished round still adds up; the mistake
    # bank simply has nothing to point at.
    question = models.ForeignKey('quizzes.Question', on_delete=models.SET_NULL, null=True, related_name='live_answers')
    index = models.PositiveSmallIntegerField()
    choice = models.CharField(max_length=500)
    is_correct = models.BooleanField(default=False)
    ms = models.PositiveIntegerField(default=0)
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['session', 'user', 'index'], name='one_answer_per_live_question')]


class LiveVote(models.Model):
    """One player's "next question" on the reveal of question `index`."""
    session = models.ForeignKey(LiveSession, on_delete=models.CASCADE, related_name='votes')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='live_votes')
    index = models.PositiveSmallIntegerField()
    voted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['session', 'user', 'index'], name='one_vote_per_live_reveal')]
