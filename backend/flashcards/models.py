from django.db import models
from django.contrib.auth.models import User
from materials.models import Topic

class Flashcard(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flashcards')
    topic = models.ForeignKey(Topic, on_delete=models.SET_NULL, null=True, related_name='flashcards')
    # The notebook this card was generated from. Cards used to be tied to their
    # notebook only by the `source:1,2` string in `tags`, which meant deleting a
    # notebook left its cards in the study queue forever, asking about a
    # document the learner can no longer open. A real FK makes that deletion a
    # database-level cascade rather than something every caller has to remember.
    # Null for cards created by hand through the API, which belong to no
    # notebook; string reference because notebooks imports flashcards.
    notebook = models.ForeignKey(
        'notebooks.Notebook', on_delete=models.CASCADE, null=True, blank=True,
        related_name='flashcards',
        help_text='Deleted along with its notebook.',
    )
    # The documents this card was generated from. Empty for a card written by
    # hand through the API. Deleting a source unlinks it here; the card stays.
    sources = models.ManyToManyField(
        'notebooks.Source', related_name='flashcards', blank=True,
        help_text='The documents this card was generated from.',
    )
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

    # Regeneration lineage. A card the learner keeps failing is replaced by a
    # freshly generated question on the same concept; the original is archived
    # rather than deleted so its review history survives.
    origin = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='variants',
        help_text='The card this one was regenerated from.',
    )
    archived = models.BooleanField(
        default=False,
        help_text='Retired by regeneration; excluded from every study queue.',
    )
    needs_regeneration = models.BooleanField(
        default=False,
        help_text='Graded hard; replace with a new question when next due.',
    )
    generation = models.PositiveIntegerField(
        default=0,
        help_text='How many times this concept has been regenerated.',
    )
    regeneration_attempts = models.PositiveSmallIntegerField(
        default=0,
        help_text='Failed regeneration attempts since this card was flagged.',
    )

    def __str__(self):
        return self.question[:100]

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['topic', '-created_at']),
            # Study queues read active cards only, and the due-fetch looks for
            # flagged ones. Both run on every study page load.
            models.Index(fields=['user', 'archived']),
            models.Index(fields=['user', 'needs_regeneration', 'archived']),
            # No index on `notebook`: a ForeignKey is indexed by default, and
            # declaring a second one over the same column makes Postgres
            # refuse the migration ("pending trigger events") for nothing.
        ]
