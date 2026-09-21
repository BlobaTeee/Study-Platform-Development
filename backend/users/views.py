import logging

from django.utils.translation import gettext as _
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import UserProfile
from .serializers import UserProfileSerializer

logger = logging.getLogger(__name__)

# Sign-up and sign-in are Supabase's: the frontend obtains a JWT there and
# `users.authentication.SupabaseJWTAuthentication` provisions the Django user
# on first request. The password-based register/token endpoints that used to
# live here created a second Django user for the same email — one that could
# never authenticate — so they are gone rather than merely unused.


class UserProfileViewSet(viewsets.ModelViewSet):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return UserProfile.objects.filter(user=self.request.user)

    @action(detail=False, methods=['get', 'delete'])
    def me(self, request):
        if request.method == 'DELETE':
            return self._delete_account(request)
        profile = UserProfile.objects.get(user=request.user)
        serializer = self.get_serializer(profile)
        return Response(serializer.data)

    def _delete_account(self, request):
        """Everything of theirs, here and at Supabase.

        The auth user goes first: if that fails nothing local is touched, so
        the student can simply try again. Without a service-role key (dev
        boxes) the local data still goes and the leftover auth row is logged
        for the operator — a student who asked to be deleted must not be
        told no because of our configuration.
        """
        from .services import supabase_admin

        user = request.user
        uid = user.profile.supabase_uid
        if supabase_admin.is_configured():
            if not supabase_admin.delete_auth_user(uid):
                return Response(
                    {'detail': _('Could not delete the account right now. Try again in a minute.')},
                    status=503)
        else:
            logger.warning('SUPABASE_SERVICE_ROLE_KEY not set: auth user %s left at Supabase '
                           'after local deletion', uid)
        user.delete()  # cascades to profile, notebooks, cards, quizzes, tests
        return Response(status=204)

    @action(detail=False, methods=['put'])
    def update_profile(self, request):
        profile = UserProfile.objects.get(user=request.user)
        serializer = self.get_serializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)
