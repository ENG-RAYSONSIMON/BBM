from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from catalog.models import Category, Product, ProductBatch
from core.tenancy import TenantMismatch, tenant_context

from .helpers import make_owner, make_product


class CatalogModelTests(TestCase):
    def setUp(self):
        _, self.business = make_owner("a@example.com", "Shop A")
        _, self.other = make_owner("b@example.com", "Shop B")

    def test_category_names_are_unique_per_business_ignoring_case(self):
        with tenant_context(self.business):
            Category.objects.create(name="Skincare")
            with self.assertRaises(IntegrityError), transaction.atomic():
                Category.objects.create(name="SKINCARE")
        with tenant_context(self.other):
            Category.objects.create(name="Skincare")  # another business may reuse it

    def test_sku_is_unique_per_business_but_blank_is_allowed_repeatedly(self):
        make_product(self.business, "One", sku="SKU-1")
        make_product(self.business, "Two")
        make_product(self.business, "Three")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_product(self.business, "Four", sku="SKU-1")
        make_product(self.other, "Elsewhere", sku="SKU-1")

    def test_product_cannot_use_another_business_category(self):
        with tenant_context(self.other):
            foreign = Category.objects.create(name="Theirs")
        with self.assertRaises(TenantMismatch):
            make_product(self.business, category=foreign)

    def test_batch_cannot_belong_to_another_business_product(self):
        foreign = make_product(self.other)
        with tenant_context(self.business), self.assertRaises(TenantMismatch):
            ProductBatch.objects.create(product=foreign, batch_number="X")

    def test_negative_prices_rejected_by_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_product(self.business, selling_price=Decimal("-1"))

    def test_batch_numbers_unique_per_product(self):
        product = make_product(self.business)
        with tenant_context(self.business):
            ProductBatch.objects.create(product=product, batch_number="L1")
            with self.assertRaises(IntegrityError), transaction.atomic():
                ProductBatch.objects.create(product=product, batch_number="L1")
            ProductBatch.objects.create(product=make_product(self.business, "Other"), batch_number="L1")
        self.assertEqual(Product.all_objects.count(), 2)
