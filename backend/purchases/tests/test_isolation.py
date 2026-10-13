"""NFR-7: business B can't read, change, receive, cancel or reference
business A's purchases, suppliers and products."""

from catalog.models import Supplier
from catalog.tests.helpers import make_product
from core.tenancy import tenant_context
from inventory.models import StockMovement
from purchases.models import Purchase, PurchaseItem

from .helpers import PURCHASES_URL, PurchasesAPITestCase, cancel_url, detail_url, receive_url


class CrossTenantTests(PurchasesAPITestCase):
    def setUp(self):
        super().setUp()
        self.purchase_id = self.draft().data["id"]
        self.as_user(self.owner_b, self.business_b)  # B's owner holds every permission

    def test_detail_and_actions_are_404(self):
        cases = [
            ("get", detail_url(self.purchase_id), {}),
            ("put", detail_url(self.purchase_id), {"items": [self.pads_line()]}),
            ("post", receive_url(self.purchase_id), {}),
            ("post", cancel_url(self.purchase_id), {"reason": "x"}),
        ]
        for method, url, body in cases:
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(self.client, method)(url, body, format="json").status_code, 404)
        purchase = Purchase.all_objects.get()
        self.assertEqual(purchase.status, "DRAFT")
        self.assertEqual(PurchaseItem.all_objects.filter(purchase=purchase).count(), 2)
        self.assertEqual(StockMovement.all_objects.count(), 0)

    def test_list_shows_nothing_of_another_business(self):
        self.assertEqual(self.client.get(PURCHASES_URL).data["count"], 0)

    def test_foreign_ids_cannot_be_used(self):
        own = make_product(self.business_b, "B product", tracks_expiry=False)
        with tenant_context(self.business_b):
            own_supplier = Supplier.objects.create(name="B supplier")

        foreign_product = self.client.post(PURCHASES_URL, {"items": [self.pads_line()]}, format="json")
        self.assertEqual(foreign_product.status_code, 400)
        self.assertIn("items", foreign_product.data)

        foreign_supplier = self.client.post(
            PURCHASES_URL,
            {
                "supplier": str(self.supplier.pk),
                "items": [{"product": str(own.pk), "quantity": 1, "unit_cost": "10"}],
            },
            format="json",
        )
        self.assertEqual(foreign_supplier.status_code, 400)
        self.assertIn("supplier", foreign_supplier.data)

        ok = self.client.post(
            PURCHASES_URL,
            {
                "supplier": str(own_supplier.pk),
                "items": [{"product": str(own.pk), "quantity": 1, "unit_cost": "10"}],
            },
            format="json",
        )
        self.assertEqual(ok.status_code, 201)
        self.assertEqual(Purchase.all_objects.filter(business=self.business_b).count(), 1)
