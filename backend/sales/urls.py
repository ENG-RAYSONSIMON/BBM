from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import CustomerViewSet, SalePaymentView, SalesSummaryView, SaleViewSet, SaleVoidView

router = SimpleRouter()
router.register("sales", SaleViewSet, basename="sale")
router.register("customers", CustomerViewSet, basename="customer")

app_name = "sales"

urlpatterns = [
    # Before the router, so "summary" isn't read as a sale id.
    path("sales/summary/", SalesSummaryView.as_view(), name="summary"),
    path("sales/<uuid:pk>/payments/", SalePaymentView.as_view(), name="sale-payments"),
    path("sales/<uuid:pk>/void/", SaleVoidView.as_view(), name="sale-void"),
    *router.urls,
]
