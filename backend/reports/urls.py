from django.urls import path

from . import views

app_name = "reports"

REPORTS = [
    ("sales", views.SalesReportView, views.SalesReportExportView),
    ("profit", views.ProfitReportView, views.ProfitReportExportView),
    ("expenses", views.ExpensesReportView, views.ExpensesReportExportView),
    ("stock-valuation", views.StockValuationReportView, views.StockValuationReportExportView),
    ("expiry", views.ExpiryReportView, views.ExpiryReportExportView),
]

urlpatterns = [
    url
    for kind, view, export in REPORTS
    for url in (
        path(f"reports/{kind}/", view.as_view(), name=kind),
        path(f"reports/{kind}/export/", export.as_view(), name=f"{kind}-export"),
    )
]
