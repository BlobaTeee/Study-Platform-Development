"""The one Supabase Admin API call the backend makes: removing an auth user
when the student deletes their account. Needs the service-role key, which
must never reach the browser — it lives in backend/.env only."""
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY)


def delete_auth_user(supabase_uid: str) -> bool:
    """True when the auth user is gone (deleted now, or already absent)."""
    key = settings.SUPABASE_SERVICE_ROLE_KEY
    try:
        res = requests.delete(
            f'{settings.SUPABASE_URL}/auth/v1/admin/users/{supabase_uid}',
            headers={'apikey': key, 'Authorization': f'Bearer {key}'},
            timeout=10,
        )
    except requests.RequestException as exc:
        logger.error('Supabase admin delete failed for %s: %s', supabase_uid, exc)
        return False
    if res.status_code in (200, 204, 404):
        return True
    logger.error('Supabase admin delete for %s returned %s: %s',
                 supabase_uid, res.status_code, res.text[:200])
    return False
