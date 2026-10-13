from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import PurchaseCancelView, PurchaseReceiveView, PurchaseViewSet

router = SimpleRouter()
router.register("purchases", PurchaseViewSet, basename="purchase")

app_name = "purchases"

urlpatterns = [
    path("purchases/<uuid:pk>/receive/", PurchaseReceiveView.as_view(), name="purchase-receive"),
    path("purchases/<uuid:pk>/cancel/", PurchaseCancelView.as_view(), name="purchase-cancel"),
    *router.urls,
]
