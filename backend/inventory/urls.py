from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    BatchDetailView,
    ExpiringView,
    InventorySummaryView,
    LowStockView,
    ProductBatchListView,
    StockMovementViewSet,
)

router = SimpleRouter()
router.register("stock-movements", StockMovementViewSet, basename="stock-movement")

app_name = "inventory"

urlpatterns = [
    path("products/<uuid:product_id>/batches/", ProductBatchListView.as_view(), name="product-batches"),
    path("batches/<uuid:pk>/", BatchDetailView.as_view(), name="batch-detail"),
    path("inventory/low-stock/", LowStockView.as_view(), name="low-stock"),
    path("inventory/expiring/", ExpiringView.as_view(), name="expiring"),
    path("inventory/summary/", InventorySummaryView.as_view(), name="summary"),
    *router.urls,
]
