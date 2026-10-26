import django_filters
from drf_spectacular.utils import extend_schema, extend_schema_view

from accounts.rbac import AUDIT_VIEW
from core.views import TenantModelViewSet

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogFilter(django_filters.FilterSet):
    # actor_id, not a model choice field: users aren't tenant-scoped, so a
    # lookup would tell whether an id exists in another business.
    actor = django_filters.UUIDFilter(field_name="actor_id")
    date_from = django_filters.DateFilter(field_name="created_at__date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="created_at__date", lookup_expr="lte")

    class Meta:
        model = AuditLog
        fields = ("action", "target_type")


@extend_schema_view(
    list=extend_schema(tags=["audit"], summary="List audit log entries, newest first"),
    retrieve=extend_schema(tags=["audit"], summary="Get an audit log entry"),
)
class AuditLogViewSet(TenantModelViewSet):
    """FR-20: read-only. Entries are written by the actions themselves and
    can't be changed or deleted."""

    model = AuditLog
    serializer_class = AuditLogSerializer
    required_permissions = (AUDIT_VIEW,)
    http_method_names = ["get", "head", "options"]
    filterset_class = AuditLogFilter
    search_fields = ("target_label",)
    ordering_fields = ("created_at",)
    ordering = ("-created_at",)

    def get_queryset(self):
        return AuditLog.objects.select_related("actor")
