from django.urls import reverse

from accounts.models import BusinessSettings
from catalog.models import ProductBatch
from catalog.tests.helpers import TenantAPITestCase, days, make_product, stock
from core.tenancy import tenant_context
from inventory.models import StockMovement

MOVEMENTS = reverse("inventory:stock-movement-list")
LOW_STOCK = reverse("inventory:low-stock")
EXPIRING = reverse("inventory:expiring")
SUMMARY = reverse("inventory:summary")


class StockAdjustmentAPITests(TenantAPITestCase):
    def setUp(self):
        super().setUp()
        self.product = make_product(self.business_a)
        self.as_user(self.admin_a, self.business_a)  # Admin may adjust stock

    def adjust(self, **data):
        body = {"product": str(self.product.pk), "movement_type": "ADJUSTMENT", "reason": "Opening stock", **data}
        return self.client.post(MOVEMENTS, body, format="json")

    def test_stock_in_creates_the_batch_and_records_who_did_it(self):
        response = self.adjust(quantity=20, batch_number="L-001", expiry_date=days(100).isoformat())

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["quantity"], 20)
        self.assertEqual(response.data["batch_number"], "L-001")
        self.assertEqual(response.data["created_by_name"], "admin-a@example.com")
        detail = self.client.get(reverse("catalog:product-detail", args=[self.product.pk])).data
        self.assertEqual(detail["stock_on_hand"], 20)

    def test_new_batch_of_expiry_tracked_product_needs_expiry(self):
        response = self.adjust(quantity=5, batch_number="L-002")
        self.assertEqual(response.status_code, 400)
        self.assertIn("expiry_date", response.data)

    def test_stock_out_beyond_batch_stock_is_refused_and_nothing_written(self):
        batch = stock(self.business_a, self.product, 5, self.owner_a)

        response = self.adjust(movement_type="DAMAGE", quantity=-6, batch=str(batch.pk), reason="Dropped")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["quantity"], ["Only 5 in stock in this batch."])
        self.assertEqual(StockMovement.all_objects.count(), 1)

    def test_damage_must_be_negative(self):
        batch = stock(self.business_a, self.product, 5, self.owner_a)
        response = self.adjust(movement_type="DAMAGE", quantity=2, batch=str(batch.pk))
        self.assertEqual(response.status_code, 400)

    def test_reason_is_required(self):
        self.assertEqual(self.adjust(quantity=1, reason="").status_code, 400)

    def test_purchase_and_sale_are_not_manual_types(self):
        for movement_type in ("PURCHASE", "SALE", "TRANSFER"):
            with self.subTest(movement_type=movement_type):
                response = self.adjust(movement_type=movement_type, quantity=1, batch_number="X",
                                       expiry_date=days(9).isoformat())
                self.assertEqual(response.status_code, 400)

    def test_stock_out_needs_a_batch_for_expiry_tracked_products(self):
        response = self.adjust(quantity=-1)
        self.assertEqual(response.status_code, 400)
        self.assertIn("batch", response.data)

    def test_product_without_expiry_uses_default_batch_and_failed_stock_out_leaves_none(self):
        comb = make_product(self.business_a, "Comb", tracks_expiry=False)

        refused = self.adjust(product=str(comb.pk), quantity=-1)
        self.assertEqual(refused.status_code, 400)
        self.assertFalse(ProductBatch.all_objects.filter(product=comb).exists())

        added = self.adjust(product=str(comb.pk), quantity=12)
        self.assertEqual(added.status_code, 201, added.data)
        self.assertEqual(added.data["batch_number"], ProductBatch.DEFAULT_NUMBER)

    def test_movement_history_filters(self):
        stock(self.business_a, self.product, 5, self.owner_a)
        other = make_product(self.business_a, "Other")
        stock(self.business_a, other, 3, self.owner_a)

        response = self.client.get(MOVEMENTS, {"product": str(self.product.pk)})

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["product_name"], self.product.name)

    def test_ledger_rows_cannot_be_changed_over_the_api(self):
        stock(self.business_a, self.product, 5, self.owner_a)
        pk = StockMovement.all_objects.get().pk
        url = reverse("inventory:stock-movement-detail", args=[pk])
        self.as_user(self.owner_a, self.business_a)
        # PATCH: no such route (405). DELETE: not in the view's permission map,
        # so HasTenantPermission refuses it first (403). Both leave the row alone.
        self.assertEqual(self.client.patch(url, {"quantity": 99}, format="json").status_code, 405)
        self.assertIn(self.client.delete(url).status_code, (403, 405))
        self.assertEqual(StockMovement.all_objects.get(pk=pk).quantity, 5)


class BatchAPITests(TenantAPITestCase):
    def setUp(self):
        super().setUp()
        self.product = make_product(self.business_a)
        self.url = reverse("inventory:product-batches", args=[self.product.pk])
        self.as_user(self.owner_a, self.business_a)

    def test_create_and_list_batches_with_stock(self):
        created = self.client.post(self.url, {"batch_number": "L1", "expiry_date": days(40).isoformat()}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["stock_on_hand"], 0)
        stock(self.business_a, self.product, 8, self.owner_a, batch_number="L1")

        listed = self.client.get(self.url).data
        self.assertEqual([(b["batch_number"], b["stock_on_hand"]) for b in listed["results"]], [("L1", 8)])

    def test_duplicate_batch_number_and_missing_expiry_are_400(self):
        self.client.post(self.url, {"batch_number": "L1", "expiry_date": days(40).isoformat()}, format="json")
        dup = self.client.post(self.url, {"batch_number": "l1", "expiry_date": days(40).isoformat()}, format="json")
        self.assertEqual(dup.status_code, 400)
        missing = self.client.post(self.url, {"batch_number": "L2"}, format="json")
        self.assertEqual(missing.status_code, 400)

    def test_patch_expiry_date(self):
        batch = stock(self.business_a, self.product, 2, self.owner_a)
        url = reverse("inventory:batch-detail", args=[batch.pk])

        response = self.client.patch(url, {"expiry_date": days(5).isoformat()}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["expiry_date"], days(5).isoformat())
        self.assertEqual(response.data["stock_on_hand"], 2)


class AlertAPITests(TenantAPITestCase):
    def setUp(self):
        super().setUp()
        self.as_user(self.owner_a, self.business_a)

    def test_low_stock_uses_reorder_level_or_business_threshold(self):
        default = make_product(self.business_a, "Default threshold")   # 5
        custom = make_product(self.business_a, "Custom", reorder_level=30)
        fine = make_product(self.business_a, "Fine")
        archived = make_product(self.business_a, "Archived", is_active=False)
        stock(self.business_a, default, 5, self.owner_a)
        stock(self.business_a, custom, 25, self.owner_a)
        stock(self.business_a, fine, 6, self.owner_a)
        stock(self.business_a, archived, 1, self.owner_a)
        out = make_product(self.business_a, "Empty")

        names = [p["name"] for p in self.client.get(LOW_STOCK).data["results"]]

        self.assertEqual(names, [out.name, default.name, custom.name])  # lowest stock first

    def test_expiry_windows_only_list_batches_with_stock(self):
        product = make_product(self.business_a)
        stock(self.business_a, product, 3, self.owner_a, batch_number="IN-5", expiry_date=days(5))
        stock(self.business_a, product, 3, self.owner_a, batch_number="IN-45", expiry_date=days(45))
        stock(self.business_a, product, 3, self.owner_a, batch_number="GONE", expiry_date=days(2))
        stock(self.business_a, product, -3, self.owner_a, batch_number="GONE", movement_type="EXPIRY")
        with tenant_context(self.business_a):
            ProductBatch.objects.create(product=product, batch_number="OLD", expiry_date=days(-3))
        stock(self.business_a, product, 2, self.owner_a, batch_number="OLD")

        def numbers(query):
            response = self.client.get(EXPIRING, query)
            self.assertEqual(response.status_code, 200, response.data)
            return [b["batch_number"] for b in response.data["results"]]

        self.assertEqual(numbers({"within": 7}), ["IN-5"])
        self.assertEqual(numbers({"within": 60}), ["IN-5", "IN-45"])
        self.assertEqual(numbers({}), ["IN-5"])  # default: expiry_warning_days = 30
        self.assertEqual(numbers({"expired": "true"}), ["OLD"])
        first = self.client.get(EXPIRING, {"within": 7}).data["results"][0]
        self.assertEqual(first["days_left"], 5)
        self.assertEqual(first["stock_on_hand"], 3)

    def test_invalid_window_is_400(self):
        for value in ("0", "400", "soon"):
            with self.subTest(value=value):
                self.assertEqual(self.client.get(EXPIRING, {"within": value}).status_code, 400)

    def test_summary_counts(self):
        with tenant_context(self.business_a):
            BusinessSettings.objects.update(expiry_warning_days=10)
        low = make_product(self.business_a, "Low")
        stock(self.business_a, low, 2, self.owner_a, expiry_date=days(8))
        make_product(self.business_a, "Out")
        ok = make_product(self.business_a, "Ok")
        stock(self.business_a, ok, 50, self.owner_a, expiry_date=days(20))

        response = self.client.get(SUMMARY)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {"low_stock": 2, "out_of_stock": 1, "expiring_soon": 1, "expired": 0, "expiry_warning_days": 10},
        )
