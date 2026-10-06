from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import BrandViewSet, CategoryViewSet, ProductImageView, ProductViewSet, SupplierViewSet

router = SimpleRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("brands", BrandViewSet, basename="brand")
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("products", ProductViewSet, basename="product")

app_name = "catalog"

urlpatterns = [
    path("products/<uuid:pk>/image/", ProductImageView.as_view(), name="product-image"),
    *router.urls,
]
