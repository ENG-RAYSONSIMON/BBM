from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = (
            "id",
            "kind",
            "channel",
            "params",
            "target_type",
            "target_id",
            "is_read",
            "resolved_at",
            "created_at",
        )
        read_only_fields = fields


class UnreadCountSerializer(serializers.Serializer):
    unread = serializers.IntegerField()
