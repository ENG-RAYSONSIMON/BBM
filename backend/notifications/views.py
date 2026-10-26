import django_filters
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.services import get_permission_codenames

from .models import Notification
from .serializers import NotificationSerializer, UnreadCountSerializer
from .services import mark_all_read, mark_read, unread, visible_to


class NotificationFilter(django_filters.FilterSet):
    unread = django_filters.BooleanFilter(method="filter_unread", label="Only open notifications not yet read.")
    open = django_filters.BooleanFilter(field_name="resolved_at", lookup_expr="isnull", label="Only open ones.")

    class Meta:
        model = Notification
        fields = ("kind",)

    def filter_unread(self, queryset, name, value):
        return unread(queryset) if value else queryset


@extend_schema_view(
    list=extend_schema(tags=["notifications"], summary="List my notifications, newest first"),
    retrieve=extend_schema(tags=["notifications"], summary="Get a notification"),
)
class NotificationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """FR-19 notification centre. Read-only apart from read state, so not a
    TenantModelViewSet (no create/update/delete); rows still come from the
    scoped manager through visible_to(). Any member may call it; each
    notification is visible only with its required permission."""

    serializer_class = NotificationSerializer
    required_permissions = ()
    filterset_class = NotificationFilter
    ordering_fields = ("created_at",)
    ordering = ("-created_at",)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation has no membership
            return Notification.objects.none()
        codenames = get_permission_codenames(self.request.membership)
        return visible_to(self.request.user, codenames)

    @extend_schema(tags=["notifications"], summary="Mark a notification read", request=None, responses={204: None})
    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        mark_read(self.get_object(), request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(tags=["notifications"], summary="Mark all my notifications read", request=None, responses={204: None})
    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        mark_all_read(self.get_queryset(), request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(tags=["notifications"], summary="How many open notifications I haven't read", responses=UnreadCountSerializer)
    @action(detail=False, methods=["get"], url_path="unread-count", filter_backends=[], pagination_class=None)
    def unread_count(self, request):
        return Response({"unread": unread(self.get_queryset()).count()})
