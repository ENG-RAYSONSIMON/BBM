"""Shared setup for sales tests."""

from decimal import Decimal

from django.urls import reverse

from catalog.tests.helpers import TenantAPITestCase, days, make_product, stock
from core.tenancy import tenant_context
from inventory.services import with_batch_stock, with_product_stock
from catalog.models import Product, ProductBatch

SALES_URL = reverse("sales:sale-list")


def D(value):
    return Decimal(str(value))


class SalesAPITestCase(TenantAPITestCase):
    """Business A has Shea Butter (sell 12,000 / cost 8,000) with 10 units in
    batch B1, expiring in 200 days."""

    def setUp(self):
        super().setUp()
        self.product = make_product(self.business_a)
        self.batch = stock(self.business_a, self.product, 10, self.owner_a, expiry_date=days(200))
        self.as_user(self.owner_a, self.business_a)

    def sell(self, items=None, amount_received="12000", **extra):
        if items is None:
            items = [{"product": str(self.product.pk), "quantity": 1}]
        return self.client.post(
            SALES_URL, {"items": items, "amount_received": amount_received, **extra}, format="json"
        )

    def batch_stock(self, batch, business=None):
        with tenant_context(business or self.business_a):
            return with_batch_stock(ProductBatch.objects.filter(pk=batch.pk)).get().stock_on_hand

    def product_stock(self, product, business=None):
        with tenant_context(business or self.business_a):
            return with_product_stock(Product.objects.filter(pk=product.pk)).get().stock_on_hand
