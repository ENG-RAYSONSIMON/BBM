from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "action",
            "actor",
            "actor_name",
            "target_type",
            "target_id",
            "target_label",
            "changes",
            "ip_address",
            "created_at",
        )
        read_only_fields = fields

    def get_actor_name(self, obj) -> str:
        user = obj.actor
        return (user.get_full_name() or user.email) if user else ""
