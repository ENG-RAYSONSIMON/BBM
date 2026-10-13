import mimetypes
import uuid

import django_filters
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from accounts.rbac import EXPENSES_DELETE, EXPENSES_MANAGE, EXPENSES_VIEW
from core.views import TenantModelViewSet

from .models import Expense, ExpenseCategory
from .serializers import (
    ExpenseCategorySerializer,
    ExpenseSerializer,
    ExpensesSummarySerializer,
    ReceiptUploadSerializer,
)
from .services import expenses_summary
from .validators import validate_receipt

EXPENSE_PERMISSIONS = {
    "GET": (EXPENSES_VIEW,),
    "POST": (EXPENSES_MANAGE,),
    "PATCH": (EXPENSES_MANAGE,),
    # SRS 2.2: Admin can't delete.
    "DELETE": (EXPENSES_DELETE,),
}


@extend_schema_view(
    list=extend_schema(tags=["expenses"], summary="List expense categories"),
    retrieve=extend_schema(tags=["expenses"], summary="Get an expense category"),
    create=extend_schema(tags=["expenses"], summary="Create an expense category"),
    partial_update=extend_schema(tags=["expenses"], summary="Update an expense category"),
    destroy=extend_schema(
        tags=["expenses"],
        summary="Delete an expense category",
        responses={204: None, 409: OpenApiResponse(description="The category has expenses.")},
    ),
)
class ExpenseCategoryViewSet(TenantModelViewSet):
    model = ExpenseCategory
    serializer_class = ExpenseCategorySerializer
    required_permissions = EXPENSE_PERMISSIONS
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    search_fields = ("name",)
    ordering_fields = ("name", "created_at")
    ordering = ("name",)
    protected_message = _("This category has expenses and can't be deleted.")


class ExpenseFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name="expense_date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="expense_date", lookup_expr="lte")

    class Meta:
        model = Expense
        fields = ("category",)


@extend_schema_view(
    list=extend_schema(tags=["expenses"], summary="List expenses"),
    retrieve=extend_schema(tags=["expenses"], summary="Get an expense"),
    create=extend_schema(tags=["expenses"], summary="Record an expense"),
    partial_update=extend_schema(tags=["expenses"], summary="Update an expense"),
    destroy=extend_schema(tags=["expenses"], summary="Delete an expense and its receipt"),
)
class ExpenseViewSet(TenantModelViewSet):
    """FR-15 expenses."""

    model = Expense
    serializer_class = ExpenseSerializer
    required_permissions = EXPENSE_PERMISSIONS
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    filterset_class = ExpenseFilter
    search_fields = ("description", "paid_to")
    ordering_fields = ("expense_date", "amount", "created_at")
    ordering = ("-expense_date", "-created_at")

    def get_queryset(self):
        return Expense.objects.select_related("category", "recorded_by")

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)

    @transaction.atomic
    def perform_destroy(self, instance):
        storage, name = instance.receipt.storage, instance.receipt.name
        super().perform_destroy(instance)
        if name:
            transaction.on_commit(lambda: storage.delete(name))


class ExpenseReceiptView(generics.GenericAPIView):
    """FR-15: attach (replace), download or remove an expense's receipt.
    Receipts are served only here, to members of the owning business."""

    serializer_class = ReceiptUploadSerializer
    parser_classes = (MultiPartParser,)
    required_permissions = {
        "GET": (EXPENSES_VIEW,),
        "PUT": (EXPENSES_MANAGE,),
        "DELETE": (EXPENSES_MANAGE,),
    }

    def get_queryset(self):
        return Expense.objects.select_related("category", "recorded_by")

    def _expense_data(self, expense):
        return ExpenseSerializer(expense, context=self.get_serializer_context()).data

    @extend_schema(
        tags=["expenses"],
        summary="Download an expense's receipt",
        responses={
            (200, "application/octet-stream"): OpenApiTypes.BINARY,
            404: OpenApiResponse(description="No receipt."),
        },
    )
    def get(self, request, pk):
        expense = self.get_object()
        if not expense.receipt:
            raise Http404(_("This expense has no receipt."))
        name = expense.receipt.name
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        response = FileResponse(expense.receipt.open("rb"), content_type=content_type)
        # Never rendered under the API's origin: an uploaded PDF could carry scripts.
        response["Content-Disposition"] = f'attachment; filename="receipt-{expense.pk}{name[name.rfind("."):]}"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "sandbox"
        return response

    @extend_schema(
        tags=["expenses"],
        summary="Attach a receipt to an expense",
        request={"multipart/form-data": ReceiptUploadSerializer},
        responses={200: ExpenseSerializer, 400: OpenApiResponse(description="Invalid file.")},
    )
    def put(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["receipt"]
        try:
            extension = validate_receipt(upload)
        except DjangoValidationError as exc:
            raise ValidationError({"receipt": exc.messages})

        with transaction.atomic():
            # Locked so concurrent uploads replace one another in turn.
            expense = get_object_or_404(self.get_queryset().select_for_update(of=("self",)), pk=pk)
            old_name = expense.receipt.name or None
            storage = expense.receipt.storage
            expense.receipt.save(f"{uuid.uuid4().hex}.{extension}", upload, save=False)
            new_name = expense.receipt.name
            try:
                expense.save(update_fields=["receipt", "updated_at"])
            except Exception:
                storage.delete(new_name)
                raise
            if old_name:
                transaction.on_commit(lambda: storage.delete(old_name))
        return Response(self._expense_data(expense))

    @extend_schema(tags=["expenses"], summary="Remove an expense's receipt", request=None, responses={200: ExpenseSerializer})
    def delete(self, request, pk):
        with transaction.atomic():
            expense = get_object_or_404(self.get_queryset().select_for_update(of=("self",)), pk=pk)
            if expense.receipt:
                storage, name = expense.receipt.storage, expense.receipt.name
                expense.receipt = None
                expense.save(update_fields=["receipt", "updated_at"])
                transaction.on_commit(lambda: storage.delete(name))
        return Response(self._expense_data(expense))


def parse_date_param(request, name, default):
    """A YYYY-MM-DD query parameter, or `default` when absent."""
    value = request.query_params.get(name)
    if not value:
        return default
    try:
        return ExpensesSummarySerializer().fields["date_from"].to_internal_value(value)
    except ValidationError:
        raise ValidationError({name: [_("Use a date like 2026-10-10.")]})


@extend_schema(
    tags=["expenses"],
    summary="Expense totals for a date range, by category",
    parameters=[
        OpenApiParameter("date_from", OpenApiTypes.DATE, description="Default: today (Africa/Dar_es_Salaam)."),
        OpenApiParameter("date_to", OpenApiTypes.DATE, description="Default: date_from."),
    ],
    responses=ExpensesSummarySerializer,
)
class ExpensesSummaryView(generics.GenericAPIView):
    serializer_class = ExpensesSummarySerializer
    required_permissions = (EXPENSES_VIEW,)

    def get(self, request):
        date_from = parse_date_param(request, "date_from", timezone.localdate())
        date_to = parse_date_param(request, "date_to", date_from)
        if date_to < date_from:
            raise ValidationError({"date_to": [_("The end date is before the start date.")]})
        return Response(ExpensesSummarySerializer(expenses_summary(date_from, date_to)).data)
