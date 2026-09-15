from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import UserProfile
from .serializers import UserProfileSerializer

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

    @action(detail=False, methods=['get'])
    def me(self, request):
        profile = UserProfile.objects.get(user=request.user)
        serializer = self.get_serializer(profile)
        return Response(serializer.data)

    @action(detail=False, methods=['put'])
    def update_profile(self, request):
        profile = UserProfile.objects.get(user=request.user)
        serializer = self.get_serializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)
