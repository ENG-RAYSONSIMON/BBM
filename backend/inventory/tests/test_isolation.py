"""NFR-7: business B can't read, change or delete business A's rows through
any Phase 2 endpoint, even with valid ids, nor point its own rows at them."""

from django.urls import reverse

from catalog.models import Brand, Category, Product, Supplier
from catalog.tests.helpers import TenantAPITestCase, days, make_product, stock
from core.tenancy import tenant_context
from inventory.models import StockMovement


class CrossTenantTests(TenantAPITestCase):
    def setUp(self):
        super().setUp()
        with tenant_context(self.business_a):
            self.category = Category.objects.create(name="A cat")
            self.brand = Brand.objects.create(name="A brand")
            self.supplier = Supplier.objects.create(name="A supplier")
        self.product = make_product(
            self.business_a, category=self.category, brand=self.brand, supplier=self.supplier
        )
        self.batch = stock(self.business_a, self.product, 10, self.owner_a, expiry_date=days(20))
        self.movement = StockMovement.all_objects.get()
        self.as_user(self.owner_b, self.business_b)  # B's owner holds every permission

    def test_detail_update_and_delete_are_404(self):
        detail_urls = [
            reverse("catalog:category-detail", args=[self.category.pk]),
            reverse("catalog:brand-detail", args=[self.brand.pk]),
            reverse("catalog:supplier-detail", args=[self.supplier.pk]),
            reverse("catalog:product-detail", args=[self.product.pk]),
        ]
        for url in detail_urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.patch(url, {"name": "pwned"}, format="json").status_code, 404)
                self.assertEqual(self.client.delete(url).status_code, 404)

        others = [
            ("get", reverse("inventory:product-batches", args=[self.product.pk])),
            ("post", reverse("inventory:product-batches", args=[self.product.pk])),
            ("get", reverse("inventory:batch-detail", args=[self.batch.pk])),
            ("patch", reverse("inventory:batch-detail", args=[self.batch.pk])),
            ("get", reverse("inventory:stock-movement-detail", args=[self.movement.pk])),
            ("put", reverse("catalog:product-image", args=[self.product.pk])),
            ("delete", reverse("catalog:product-image", args=[self.product.pk])),
        ]
        for method, url in others:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, {}, format="multipart" if method == "put" else "json")
                self.assertEqual(response.status_code, 404)

        with tenant_context(self.business_a):
            self.assertEqual(Product.objects.get().name, "Shea Butter")
            self.assertEqual(Category.objects.get().name, "A cat")

    def test_lists_and_alerts_show_nothing_of_another_business(self):
        for name in ("category-list", "brand-list", "supplier-list", "product-list"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(f"catalog:{name}")).data["count"], 0)
        self.assertEqual(self.client.get(reverse("inventory:stock-movement-list")).data["count"], 0)
        self.assertEqual(self.client.get(reverse("inventory:expiring"), {"within": 60}).data["count"], 0)
        summary = self.client.get(reverse("inventory:summary")).data
        self.assertEqual(summary["expiring_soon"], 0)

    def test_foreign_ids_cannot_be_used_as_references(self):
        product = self.client.post(
            reverse("catalog:product-list"),
            {"name": "Mine", "selling_price": "1", "cost_price": "1", "category": str(self.category.pk)},
            format="json",
        )
        self.assertEqual(product.status_code, 400)
        self.assertIn("category", product.data)

        adjustment = self.client.post(
            reverse("inventory:stock-movement-list"),
            {"product": str(self.product.pk), "movement_type": "ADJUSTMENT", "quantity": -10,
             "batch": str(self.batch.pk), "reason": "steal"},
            format="json",
        )
        self.assertEqual(adjustment.status_code, 400)
        self.assertIn("product", adjustment.data)

        own = make_product(self.business_b, "B product")
        mixed = self.client.post(
            reverse("inventory:stock-movement-list"),
            {"product": str(own.pk), "movement_type": "ADJUSTMENT", "quantity": -1,
             "batch": str(self.batch.pk), "reason": "x"},
            format="json",
        )
        self.assertEqual(mixed.status_code, 400)
        self.assertIn("batch", mixed.data)
        self.assertEqual(StockMovement.all_objects.count(), 1)
