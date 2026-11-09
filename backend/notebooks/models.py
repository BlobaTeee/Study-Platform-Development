from django.db import models
from django.contrib.auth.models import User
from django.dispatch import receiver


class Notebook(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notebooks')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # {"hash", "edges": [{"from", "to", "why"}]}: the knowledge map's links, found once per set of concepts.
    concept_links = models.JSONField(blank=True, default=dict)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return self.title


@receiver(models.signals.post_save, sender=Notebook)
def _own_new_notebook(sender, instance, created, **kwargs):
    """A notebook always has an owner, from the moment it exists.

    On the model rather than in the view so that management commands,
    fixtures and the admin cannot create a notebook nobody is in.
    """
    if created:
        NotebookMember.objects.get_or_create(
            notebook=instance, user=instance.user, defaults={'role': 'owner'})


class NotebookMember(models.Model):
    """Who is in a notebook.

    The creator is its owner, written by the view that creates the notebook
    and backfilled for every notebook that predates sharing. A member sees
    the notebook's documents and the material generated from them; what they
    have studied (schedule, attempts, papers) stays their own.
    """
    ROLE_CHOICES = [('owner', 'Owner'), ('member', 'Member')]

    notebook = models.ForeignKey(Notebook, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notebook_memberships')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='member')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # One row per person per notebook, the owner first then by arrival.
        # '-role' sorts 'owner' above 'member' alphabetically, which is the
        # order a member list wants to be read in.
        constraints = [
            models.UniqueConstraint(fields=['notebook', 'user'], name='one_membership_per_user'),
        ]
        ordering = ['-role', 'joined_at']

    def __str__(self):
        return f'{self.user} in {self.notebook} ({self.role})'


class NotebookInvite(models.Model):
    """An invitation to a notebook, addressed to an email.

    Keyed on the address rather than a user because the person invited may
    not have signed up yet; the token is what the link carries. Accepting
    creates the membership and stamps `accepted_at`, so a link works once.
    """
    notebook = models.ForeignKey(Notebook, on_delete=models.CASCADE, related_name='invites')
    email = models.EmailField()
    token = models.CharField(max_length=43, unique=True, db_index=True)
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notebook_invites_sent')
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='notebook_invites_accepted')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.email} → {self.notebook}'


class ChatGroup(models.Model):
    """A chat group: a few people and a name they chose.

    Deliberately not a notebook. A notebook is where documents live; a group
    is who you talk to, and the two rarely line up — a study group spans
    several notebooks, and a notebook you keep to yourself needs no chat.
    """
    name = models.CharField(max_length=120)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_groups_created')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return self.name


class ChatGroupMember(models.Model):
    group = models.ForeignKey(ChatGroup, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_group_memberships')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['group', 'user'], name='one_chat_membership_per_user'),
        ]
        ordering = ['joined_at']


class GroupMessage(models.Model):
    """One line in a group's thread."""
    group = models.ForeignKey(ChatGroup, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='group_messages')
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        indexes = [models.Index(fields=['group', '-id'])]

    def __str__(self):
        return f'{self.user}: {self.body[:40]}'


class DirectMessage(models.Model):
    """One line of a private thread between two people.

    Addressed person to person rather than to a conversation row: a pair
    only ever has one thread, so the pair *is* the thread, and there is no
    second table to keep in step. Who may write to whom is not stored here
    — it is asked of the notebooks they share (services/chat.py).
    """
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='direct_sent')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='direct_received')
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        indexes = [
            # The thread query: everything between two people, newest first.
            models.Index(fields=['sender', 'recipient', '-id']),
            models.Index(fields=['recipient', 'sender', '-id']),
        ]

    def __str__(self):
        return f'{self.sender} → {self.recipient}: {self.body[:40]}'


class Source(models.Model):
    STATUS_CHOICES = [
        ('processing', 'Processing'),
        ('ready', 'Ready'),
        ('failed', 'Failed'),
    ]
    FILE_TYPE_CHOICES = [
        ('pdf', 'PDF'),
        ('docx', 'Word'),
        ('pptx', 'PowerPoint'),
        ('text', 'Pasted text'),
        ('url', 'Web page'),
    ]

    notebook = models.ForeignKey(Notebook, on_delete=models.CASCADE, related_name='sources')
    title = models.CharField(max_length=255)
    # Blank for pasted text and fetched pages: their text arrives already
    # extracted, so there is nothing to keep on disk.
    file = models.FileField(upload_to='notebook_sources/%Y/%m/', blank=True)
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES, default='pdf')
    # For uploads, the name the file came with; for a web page, its URL.
    original_filename = models.CharField(max_length=255, blank=True)
    page_count = models.PositiveIntegerField(default=0)
    extracted_text = models.TextField(blank=True, default='')
    gemini_summary = models.TextField(blank=True, default='')
    # The document's main ideas, read once from the whole text: a list of
    # {point, importance: core|supporting, passage}. See services/key_points.
    key_points = models.JSONField(blank=True, default=list)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='processing')
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class MapBuild(models.Model):
    """One map a student built from memory for one document. The feature is gone
    (2026-11-09); the table stays so the maps already drawn are kept.

    Stored only once graded. `cards` are the student's own: {id, label,
    match_key, match_label}, the match being the key point (as a map concept
    key) the card stands for, or None. `links` are {from, to, why, verdict,
    feedback} between card ids. `missed` are the document's links between
    recalled concepts the student did not join; `missed_points` the key
    points no card matched.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='map_builds')
    notebook = models.ForeignKey(Notebook, on_delete=models.CASCADE, related_name='map_builds')
    source = models.ForeignKey('Source', on_delete=models.SET_NULL, null=True, blank=True, related_name='map_builds')
    cards = models.JSONField(default=list)
    links = models.JSONField(default=list)
    missed = models.JSONField(default=list)
    missed_points = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    graded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


class Translation(models.Model):
    """A document text in the page's other language (services/translate.py).

    Keyed by a hash of the text, not by user or document: the same key
    point read by two students, or kept after a document is regenerated,
    is translated once.
    """
    text_hash = models.CharField(max_length=64)
    target = models.CharField(max_length=2)
    translated = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['text_hash', 'target'], name='one_translation_per_text')]
