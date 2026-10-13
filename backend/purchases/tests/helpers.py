"""Shared setup for purchases tests."""

from decimal import Decimal

from django.urls import reverse

from catalog.models import Product, ProductBatch, Supplier
from catalog.tests.helpers import TenantAPITestCase, days, make_product
from core.tenancy import tenant_context
from inventory.services import with_batch_stock, with_product_stock

PURCHASES_URL = reverse("purchases:purchase-list")


def D(value):
    return Decimal(str(value))


def receive_url(purchase_id):
    return reverse("purchases:purchase-receive", args=[purchase_id])


def cancel_url(purchase_id):
    return reverse("purchases:purchase-cancel", args=[purchase_id])


def detail_url(purchase_id):
    return reverse("purchases:purchase-detail", args=[purchase_id])


class PurchasesAPITestCase(TenantAPITestCase):
    """Business A has Shea Butter (tracks expiry, cost 8,000), Cotton Pads
    (no expiry, cost 1,500) and the supplier Dar Cosmetics. No stock yet."""

    def setUp(self):
        super().setUp()
        self.shea = make_product(self.business_a)
        self.pads = make_product(
            self.business_a, "Cotton Pads", tracks_expiry=False,
            selling_price=D("3000"), cost_price=D("1500"),
        )
        with tenant_context(self.business_a):
            self.supplier = Supplier.objects.create(name="Dar Cosmetics")
        self.as_user(self.owner_a, self.business_a)

    def shea_line(self, quantity=10, unit_cost="7500", batch_number="SB-01", expiry=200):
        return {
            "product": str(self.shea.pk),
            "quantity": quantity,
            "unit_cost": unit_cost,
            "batch_number": batch_number,
            "expiry_date": days(expiry).isoformat() if expiry is not None else None,
        }

    def pads_line(self, quantity=20, unit_cost="1200"):
        return {"product": str(self.pads.pk), "quantity": quantity, "unit_cost": unit_cost}

    def draft(self, items=None, **extra):
        if items is None:
            items = [self.shea_line(), self.pads_line()]
        body = {"supplier": str(self.supplier.pk), "reference": "INV-77", "items": items, **extra}
        return self.client.post(PURCHASES_URL, body, format="json")

    def receive(self, purchase_id):
        return self.client.post(receive_url(purchase_id))

    def product_stock(self, product, business=None):
        with tenant_context(business or self.business_a):
            return with_product_stock(Product.objects.filter(pk=product.pk)).get().stock_on_hand

    def batch_stock(self, batch_id, business=None):
        with tenant_context(business or self.business_a):
            return with_batch_stock(ProductBatch.objects.filter(pk=batch_id)).get().stock_on_hand

    def cost_price(self, product):
        return Product.all_objects.get(pk=product.pk).cost_price
