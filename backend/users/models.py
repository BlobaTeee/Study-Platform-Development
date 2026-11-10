from django.conf import settings
from django.db import models
from django.contrib.auth.models import User


def _default_timezone():
    return settings.TIME_ZONE


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    supabase_uid = models.UUIDField(unique=True, null=True, blank=True)
    bio = models.TextField(blank=True, null=True)
    avatar = models.URLField(blank=True, null=True)
    preferred_language = models.CharField(max_length=10, default='vi')
    theme = models.CharField(max_length=20, default='light', choices=[('light', 'Light'), ('dark', 'Dark')])
    # IANA zone name, reported by the browser on sign-in. Reminder emails
    # state the test time in this zone; without it every student would read
    # the server's clock. Validated on write, so anything stored resolves.
    timezone = models.CharField(max_length=64, default=_default_timezone)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s profile"

    class Meta:
        ordering = ['-created_at']
