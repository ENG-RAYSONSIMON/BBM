from unittest import mock

from django.db.models import Sum
from django.urls import reverse

from catalog.models import ProductBatch
from catalog.tests.helpers import days, make_member, make_product, stock
from core.tenancy import tenant_context
from inventory import services as inventory_services
from inventory.models import StockMovement
from purchases.models import Purchase, PurchaseItem
from purchases.services import receive_purchase
from sales.models import SaleItem

from .helpers import PURCHASES_URL, D, PurchasesAPITestCase, cancel_url, detail_url, receive_url


class DraftTests(PurchasesAPITestCase):
    def test_draft_totals_and_numbering_without_touching_stock(self):
        response = self.draft()
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data
        self.assertEqual(data["status"], "DRAFT")
        self.assertEqual(data["purchase_number"], "P-000001")
        self.assertEqual(data["supplier_name"], "Dar Cosmetics")
        self.assertEqual(D(data["total"]), D("99000"))  # 10 × 7,500 + 20 × 1,200
        self.assertEqual(len(data["items"]), 2)
        pads = next(item for item in data["items"] if str(item["product"]) == str(self.pads.pk))
        self.assertEqual(pads["batch_number"], "")  # no expiry: the DEFAULT batch on receive
        self.assertIsNone(pads["batch"])
        self.assertEqual(self.draft().data["purchase_number"], "P-000002")

        self.assertEqual(StockMovement.all_objects.count(), 0)
        self.assertEqual(ProductBatch.all_objects.count(), 0)
        self.assertEqual(self.cost_price(self.shea), D("8000"))

    def test_numbers_are_per_business(self):
        self.draft()
        self.as_user(self.owner_b, self.business_b)
        product_b = make_product(self.business_b, "B product", tracks_expiry=False)
        created = self.client.post(
            PURCHASES_URL,
            {"items": [{"product": str(product_b.pk), "quantity": 1, "unit_cost": "100"}]},
            format="json",
        )
        self.assertEqual(created.data["purchase_number"], "P-000001")

    def test_edit_replaces_the_lines(self):
        purchase_id = self.draft().data["id"]
        response = self.client.put(
            detail_url(purchase_id),
            {"supplier": None, "reference": "INV-78", "items": [self.pads_line(quantity=5, unit_cost="1000")]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["reference"], "INV-78")
        self.assertIsNone(response.data["supplier"])
        self.assertEqual(D(response.data["total"]), D("5000"))
        self.assertEqual(PurchaseItem.all_objects.count(), 1)

    def test_line_validation(self):
        cases = {
            "no batch number": [self.shea_line(batch_number="")],
            "new batch without expiry": [self.shea_line(expiry=None)],
            "same batch twice": [self.shea_line(), self.shea_line(quantity=2)],
            "zero quantity": [self.shea_line(quantity=0)],
            "negative cost": [self.shea_line(unit_cost="-1")],
            "no lines": [],
        }
        for label, items in cases.items():
            with self.subTest(label):
                response = self.draft(items)
                self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Purchase.all_objects.count(), 0)

    def test_existing_batch_needs_no_expiry_but_must_match(self):
        stock(self.business_a, self.shea, 3, self.owner_a, batch_number="SB-01", expiry_date=days(100))
        self.assertEqual(self.draft([self.shea_line(expiry=None)]).status_code, 201)
        clash = self.draft([self.shea_line(expiry=150)])
        self.assertEqual(clash.status_code, 400)
        self.assertIn("different expiry", str(clash.data))

    def test_archived_product_is_refused(self):
        self.pads.is_active = False
        with tenant_context(self.business_a):
            self.pads.save()
        response = self.draft([self.pads_line()])
        self.assertEqual(response.status_code, 400)
        self.assertIn("archived", str(response.data))


class ReceiveTests(PurchasesAPITestCase):
    def test_receive_puts_stock_on_the_shelf_and_updates_cost(self):
        purchase_id = self.draft(purchase_date=days(-1).isoformat()).data["id"]
        response = self.receive(purchase_id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "RECEIVED")
        self.assertEqual(response.data["received_by"], self.owner_a.pk)
        self.assertIsNotNone(response.data["received_at"])

        self.assertEqual(self.product_stock(self.shea), 10)
        self.assertEqual(self.product_stock(self.pads), 20)
        shea_batch = ProductBatch.all_objects.get(product=self.shea)
        self.assertEqual(shea_batch.batch_number, "SB-01")
        self.assertEqual(shea_batch.expiry_date, days(200))
        self.assertEqual(shea_batch.received_on, days(-1))
        self.assertEqual(ProductBatch.all_objects.get(product=self.pads).batch_number, ProductBatch.DEFAULT_NUMBER)
        for item in response.data["items"]:
            self.assertIsNotNone(item["batch"])

        movements = StockMovement.all_objects.filter(movement_type="PURCHASE")
        self.assertEqual(movements.count(), 2)
        self.assertEqual(movements.first().reason, "Purchase P-000001 (INV-77)")
        self.assertEqual(self.cost_price(self.shea), D("7500"))
        self.assertEqual(self.cost_price(self.pads), D("1200"))

    def test_receive_adds_to_an_existing_batch(self):
        batch = stock(self.business_a, self.shea, 4, self.owner_a, batch_number="SB-01", expiry_date=days(200))
        purchase_id = self.draft([self.shea_line(quantity=6)]).data["id"]
        self.receive(purchase_id)
        self.assertEqual(ProductBatch.all_objects.filter(product=self.shea).count(), 1)
        self.assertEqual(self.batch_stock(batch.pk), 10)

    def test_sales_snapshot_the_new_cost_and_old_sales_keep_theirs(self):
        stock(self.business_a, self.pads, 5, self.owner_a)
        sale_url = reverse("sales:sale-list")
        sell = {"items": [{"product": str(self.pads.pk), "quantity": 1}], "amount_received": "3000"}
        self.assertEqual(self.client.post(sale_url, sell, format="json").status_code, 201)

        self.receive(self.draft([self.pads_line(unit_cost="2000")]).data["id"])
        self.client.post(sale_url, sell, format="json")

        costs = list(SaleItem.all_objects.order_by("created_at").values_list("unit_cost", flat=True))
        self.assertEqual(costs, [D("1500"), D("2000")])

    def test_received_purchase_is_final(self):
        purchase_id = self.draft().data["id"]
        self.receive(purchase_id)
        again = self.receive(purchase_id)
        self.assertEqual(again.status_code, 400)
        self.assertIn("already received", str(again.data["non_field_errors"]))
        edit = self.client.put(detail_url(purchase_id), {"items": [self.pads_line()]}, format="json")
        self.assertEqual(edit.status_code, 400)
        cancel = self.client.post(cancel_url(purchase_id), {"reason": "oops"}, format="json")
        self.assertEqual(cancel.status_code, 400)
        self.assertEqual(self.product_stock(self.shea), 10)
        self.assertEqual(StockMovement.all_objects.count(), 2)

    def test_purchases_cannot_be_deleted(self):
        purchase_id = self.draft().data["id"]
        self.assertIn(self.client.delete(detail_url(purchase_id)).status_code, (403, 405))
        self.assertIn(self.client.patch(detail_url(purchase_id), {}, format="json").status_code, (403, 405))
        self.assertEqual(Purchase.all_objects.count(), 1)

    def test_product_archived_after_drafting_blocks_receive(self):
        purchase_id = self.draft().data["id"]
        self.pads.is_active = False
        with tenant_context(self.business_a):
            self.pads.save()
        response = self.receive(purchase_id)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StockMovement.all_objects.count(), 0)
        self.assertEqual(Purchase.all_objects.get().status, "DRAFT")

    def test_expiry_tracking_changed_after_drafting(self):
        """Receiving follows the product as it is now, not as it was drafted."""
        off = self.draft([self.shea_line()]).data["id"]
        self.shea.tracks_expiry = False
        with tenant_context(self.business_a):
            self.shea.save()
        self.assertEqual(self.receive(off).status_code, 200)
        self.assertEqual(
            list(ProductBatch.all_objects.filter(product=self.shea).values_list("batch_number", "expiry_date")),
            [(ProductBatch.DEFAULT_NUMBER, None)],
        )

        on = self.draft([self.pads_line()]).data["id"]
        self.pads.tracks_expiry = True
        with tenant_context(self.business_a):
            self.pads.save()
        refused = self.receive(on)
        self.assertEqual(refused.status_code, 400)
        self.assertIn("batch number", str(refused.data["items"]))
        self.assertEqual(self.product_stock(self.pads), 0)

    def test_failure_on_a_later_line_rolls_back_everything(self):
        """FR-14: stock, batches, costs and status all change together or not at all."""
        purchase_id = self.draft().data["id"]
        real = inventory_services.record_movement
        calls = []

        def fail_second(**kwargs):
            calls.append(kwargs)
            if len(calls) == 2:
                raise RuntimeError("boom")
            return real(**kwargs)

        with tenant_context(self.business_a):
            purchase = Purchase.objects.get(pk=purchase_id)
            with mock.patch("purchases.services.record_movement", side_effect=fail_second):
                with self.assertRaises(RuntimeError):
                    receive_purchase(purchase=purchase, user=self.owner_a)

        self.assertEqual(len(calls), 2)
        self.assertEqual(StockMovement.all_objects.count(), 0)
        self.assertEqual(ProductBatch.all_objects.count(), 0)
        self.assertEqual(self.cost_price(self.shea), D("8000"))
        self.assertEqual(Purchase.all_objects.get().status, "DRAFT")
        self.assertFalse(PurchaseItem.all_objects.filter(batch__isnull=False).exists())

    def test_stock_reconciles_with_the_ledger(self):
        """NFR-9 with purchases in the mix."""
        stock(self.business_a, self.pads, 5, self.owner_a)
        self.receive(self.draft([self.pads_line(quantity=20)]).data["id"])
        self.receive(self.draft([self.pads_line(quantity=7)]).data["id"])
        movements = StockMovement.all_objects.filter(product=self.pads)
        self.assertEqual(movements.aggregate(n=Sum("quantity"))["n"], 32)
        self.assertEqual(self.product_stock(self.pads), 32)


class CancelAndListTests(PurchasesAPITestCase):
    def test_cancel_a_draft(self):
        purchase_id = self.draft().data["id"]
        self.assertEqual(self.client.post(cancel_url(purchase_id), {"reason": " "}, format="json").status_code, 400)
        response = self.client.post(cancel_url(purchase_id), {"reason": "Supplier out of stock"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "CANCELLED")
        self.assertEqual(response.data["cancel_reason"], "Supplier out of stock")
        self.assertEqual(self.receive(purchase_id).status_code, 400)
        self.assertEqual(StockMovement.all_objects.count(), 0)

    def test_filters_and_search(self):
        first = self.draft(purchase_date=days(-10).isoformat()).data["id"]
        self.receive(first)
        self.draft(items=[self.pads_line()], supplier=None, reference="CASH-MKT")
        cases = {
            "status=RECEIVED": ({"status": "RECEIVED"}, 1),
            "status=DRAFT": ({"status": "DRAFT"}, 1),
            "supplier": ({"supplier": str(self.supplier.pk)}, 1),
            "date range": ({"date_from": days(-11).isoformat(), "date_to": days(-9).isoformat()}, 1),
            "number": ({"number": "P-000002"}, 1),
            "search reference": ({"search": "MKT"}, 1),
            "search supplier": ({"search": "Dar"}, 1),
        }
        for label, (params, count) in cases.items():
            with self.subTest(label):
                response = self.client.get(PURCHASES_URL, params)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["count"], count)
        listed = self.client.get(PURCHASES_URL).data["results"][0]
        self.assertEqual(listed["item_count"], 1)

    def test_role_without_purchase_permissions_gets_403(self):
        trainee = make_member(self.business_a, "nobody@example.com", "Trainee")
        purchase_id = self.draft().data["id"]
        self.as_user(trainee, self.business_a)
        self.assertEqual(self.client.get(PURCHASES_URL).status_code, 403)
        self.assertEqual(self.draft().status_code, 403)
        self.assertEqual(self.client.get(detail_url(purchase_id)).status_code, 403)
        self.assertEqual(self.receive(purchase_id).status_code, 403)
        self.assertEqual(self.client.post(cancel_url(purchase_id), {"reason": "x"}, format="json").status_code, 403)
        self.assertEqual(Purchase.all_objects.get().status, "DRAFT")

    def test_admin_can_buy_and_receive(self):
        self.as_user(self.admin_a, self.business_a)
        purchase_id = self.draft().data["id"]
        self.assertEqual(self.client.post(receive_url(purchase_id)).status_code, 200)
