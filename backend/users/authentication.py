import jwt
from django.conf import settings
from django.contrib.auth.models import User
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import UserProfile

_jwk_client = None


def _get_jwk_client():
    global _jwk_client
    if _jwk_client is None:
        if not settings.SUPABASE_URL:
            raise AuthenticationFailed('Supabase auth is not configured on the server.')
        _jwk_client = jwt.PyJWKClient(
            f'{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json'
        )
    return _jwk_client


def user_for_token(token: str):
    """The Django user behind a Supabase access token, provisioned on first
    sight. Shared by the DRF authentication class and the Socket.IO server,
    so a token means the same thing over HTTP and over a socket.

    Raises AuthenticationFailed when the token is unusable.
    """
    try:
        signing_key = _get_jwk_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=['ES256', 'RS256'],
            audience='authenticated',
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationFailed(f'Invalid Supabase token: {exc}') from exc

    supabase_uid = payload.get('sub')
    if not supabase_uid:
        raise AuthenticationFailed('Supabase token is missing a subject claim.')

    email = payload.get('email') or ''
    # Email sign-ups carry `username`; Google/GitHub carry a name instead.
    meta = payload.get('user_metadata') or {}
    username = (
        next((meta[k] for k in ('username', 'full_name', 'name', 'user_name')
              if isinstance(meta.get(k), str) and meta[k].strip()), None)
        or (email.split('@')[0] if email else supabase_uid)
    )

    profile = UserProfile.objects.filter(supabase_uid=supabase_uid).select_related('user').first()
    if profile:
        user = profile.user
        # Email and display name are Supabase's to change; mirror them.
        changed = []
        if email and user.email != email:
            user.email = email
            changed.append('email')
        if user.first_name != username[:30]:
            user.first_name = username[:30]
            changed.append('first_name')
        if changed:
            user.save(update_fields=changed)
        return user

    user = User.objects.create_user(username=f'supabase:{supabase_uid}', email=email)
    UserProfile.objects.create(user=user, supabase_uid=supabase_uid)
    user.first_name = username[:30]
    user.save(update_fields=['first_name'])
    return user


class SupabaseJWTAuthentication(BaseAuthentication):
    """Authenticates requests using a Supabase-issued access token.

    Maps the Supabase user (by uid) to a local Django User, creating one
    on first sight, so existing views/models that key off request.user
    (ForeignKey(User)) continue to work unchanged.
    """

    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return None

        token = auth_header[len('Bearer '):].strip()
        if not token:
            return None

        return (user_for_token(token), token)

    def authenticate_header(self, request):
        # Advertise the Bearer scheme so DRF answers auth failures with 401
        # (not 403). The frontend keys off 401 to redirect an expired session
        # to login instead of showing a "can't reach the server" error.
        return 'Bearer'
