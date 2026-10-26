import csv
import io

from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics
from rest_framework.response import Response

from accounts.rbac import REPORTS_EXPORT, REPORTS_VIEW
from audit.services import Action, record

from . import services
from .serializers import (
    ExpiryQuerySerializer,
    ExpiryReportSerializer,
    ExpensesReportSerializer,
    PeriodQuerySerializer,
    ProfitReportSerializer,
    SalesReportSerializer,
    StockValuationReportSerializer,
)

# CSV columns per report: (row key, header). Headers follow the request's language.
PERIOD = ("period", _("Period starting"))
COLUMNS = {
    "sales": [
        PERIOD,
        ("sales_count", _("Number of sales")),
        ("revenue", _("Revenue (TZS)")),
        ("discounts", _("Discounts (TZS)")),
        ("cogs", _("Cost of goods sold (TZS)")),
        ("gross_profit", _("Gross profit (TZS)")),
        ("cash_collected", _("Cash collected (TZS)")),
    ],
    "profit": [
        PERIOD,
        ("revenue", _("Revenue (TZS)")),
        ("cogs", _("Cost of goods sold (TZS)")),
        ("gross_profit", _("Gross profit (TZS)")),
        ("expenses", _("Expenses (TZS)")),
        ("net_profit", _("Net profit (TZS)")),
    ],
    "expenses": [
        PERIOD,
        ("category_name", _("Category")),
        ("count", _("Number of expenses")),
        ("total", _("Total (TZS)")),
    ],
    "stock-valuation": [
        ("name", _("Product")),
        ("sku", _("SKU")),
        ("category_name", _("Category")),
        ("stock_on_hand", _("Stock")),
        ("unit", _("Unit")),
        ("cost_price", _("Cost price (TZS)")),
        ("selling_price", _("Selling price (TZS)")),
        ("cost_value", _("Value at cost (TZS)")),
        ("retail_value", _("Value at selling price (TZS)")),
    ],
    "expiry": [
        ("name", _("Product")),
        ("sku", _("SKU")),
        ("batch_number", _("Batch")),
        ("expiry_date", _("Expiry date")),
        ("days_left", _("Days left")),
        ("stock_on_hand", _("Stock")),
        ("cost_value", _("Value at cost (TZS)")),
    ],
}

CSV_RESPONSE = {(200, "text/csv"): OpenApiTypes.STR, 400: OpenApiResponse(description="Invalid parameters.")}


# Text starting with these runs as a formula in Excel (CSV injection).
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, str):
        # Names come from users: make a leading formula character plain text.
        return f"'{value}" if value.startswith(FORMULA_START) else value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class ReportView(generics.GenericAPIView):
    """Base for one FR-18 report: parses the query, builds the report, and
    answers JSON. The export subclass answers the same rows as CSV."""

    kind = None
    query_serializer_class = PeriodQuerySerializer
    required_permissions = (REPORTS_VIEW,)

    def params(self):
        query = self.query_serializer_class(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        return query.validated_data

    def build(self, params):
        raise NotImplementedError

    def get(self, request):
        params = self.params()
        return Response(self.get_serializer({**params, **self.build(params)}).data)


class PeriodReportView(ReportView):
    report = None  # services function (date_from, date_to, period)

    def build(self, params):
        return type(self).report(params["date_from"], params["date_to"], params["period"])


class ExportMixin:
    """Same report as CSV (UTF-8 with BOM so Excel shows Kiswahili text
    right). Every download is audit-logged (FR-20)."""

    # Downloading is viewing too: a role needs both.
    required_permissions = (REPORTS_VIEW, REPORTS_EXPORT)

    def get(self, request):
        params = self.params()
        report = self.build(params)
        columns = COLUMNS[self.kind]
        buffer = io.StringIO()
        buffer.write("﻿")
        writer = csv.writer(buffer)
        writer.writerow([str(header) for _key, header in columns])
        for row in report["rows"]:
            writer.writerow([_cell(row[key]) for key, _header in columns])

        record(
            Action.EXPORT,
            label=self.kind,
            changes={"report": self.kind, **{k: _cell(v) for k, v in params.items()}, "rows": len(report["rows"])},
        )
        stamp = "-".join(_cell(params[k]) for k in ("date_from", "date_to") if k in params) or _cell(report["as_of"])
        response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="bbm-{self.kind}-{stamp}.csv"'
        return response


PERIOD_PARAMS = {"parameters": [PeriodQuerySerializer]}


@extend_schema(tags=["reports"], summary="Sales report by day, week, month or year", **PERIOD_PARAMS)
class SalesReportView(PeriodReportView):
    kind = "sales"
    report = services.sales_report
    serializer_class = SalesReportSerializer


@extend_schema(tags=["reports"], summary="Profit report: gross profit, expenses and net profit", **PERIOD_PARAMS)
class ProfitReportView(PeriodReportView):
    kind = "profit"
    report = services.profit_report
    serializer_class = ProfitReportSerializer


@extend_schema(tags=["reports"], summary="Expenses report by period and category", **PERIOD_PARAMS)
class ExpensesReportView(PeriodReportView):
    kind = "expenses"
    report = services.expenses_report
    serializer_class = ExpensesReportSerializer


@extend_schema(tags=["reports"], summary="Stock valuation: what's on the shelf at cost and selling price")
class StockValuationReportView(ReportView):
    kind = "stock-valuation"
    serializer_class = StockValuationReportSerializer

    def params(self):
        return {}

    def build(self, params):
        return services.stock_valuation_report()


@extend_schema(
    tags=["reports"],
    summary="Expiry report: expired and soon-expiring stock with its value",
    parameters=[ExpiryQuerySerializer],
)
class ExpiryReportView(ReportView):
    kind = "expiry"
    query_serializer_class = ExpiryQuerySerializer
    serializer_class = ExpiryReportSerializer

    def build(self, params):
        return services.expiry_report(params["within_days"])


@extend_schema(tags=["reports"], summary="Sales report as CSV", responses=CSV_RESPONSE, **PERIOD_PARAMS)
class SalesReportExportView(ExportMixin, SalesReportView):
    pass


@extend_schema(tags=["reports"], summary="Profit report as CSV", responses=CSV_RESPONSE, **PERIOD_PARAMS)
class ProfitReportExportView(ExportMixin, ProfitReportView):
    pass


@extend_schema(tags=["reports"], summary="Expenses report as CSV", responses=CSV_RESPONSE, **PERIOD_PARAMS)
class ExpensesReportExportView(ExportMixin, ExpensesReportView):
    pass


@extend_schema(tags=["reports"], summary="Stock valuation as CSV", responses=CSV_RESPONSE)
class StockValuationReportExportView(ExportMixin, StockValuationReportView):
    pass


@extend_schema(
    tags=["reports"], summary="Expiry report as CSV", responses=CSV_RESPONSE, parameters=[ExpiryQuerySerializer]
)
class ExpiryReportExportView(ExportMixin, ExpiryReportView):
    pass
