"""Which clock a student reads."""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings


def zone_for(user):
    """The student's zone from their profile; the server's if theirs is
    missing or no longer resolves (tzdata does retire names).

    Everything that turns an instant into "which day" or "what time" for a
    student goes through here — the reminder email and the activity strip
    must not disagree about what day a review happened on.
    """
    name = getattr(getattr(user, 'profile', None), 'timezone', '') or settings.TIME_ZONE
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(settings.TIME_ZONE)
