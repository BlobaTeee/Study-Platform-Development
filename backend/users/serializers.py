from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers
from .models import UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = UserProfile
        fields = ['id', 'username', 'email', 'bio', 'avatar', 'preferred_language', 'theme',
                  'timezone', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def validate_timezone(self, value):
        # A zone that does not resolve would mis-time every reminder without
        # any error at send time, so it is refused here instead.
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError(f'Unknown timezone: {value!r}')
        return value
