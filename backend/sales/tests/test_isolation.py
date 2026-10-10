"""NFR-7: business B can't read, change, pay, void or reference business A's
sales and customers, nor sell A's products."""

from django.urls import reverse

from catalog.tests.helpers import make_product, stock
from core.tenancy import tenant_context
from sales.models import Customer, Payment, Sale

from .helpers import SALES_URL, D, SalesAPITestCase


class CrossTenantTests(SalesAPITestCase):
    def setUp(self):
        super().setUp()
        with tenant_context(self.business_a):
            self.customer = Customer.objects.create(name="A customer", phone="0700")
        self.sale = self.sell(amount_received="1000", customer=str(self.customer.pk)).data
        self.as_user(self.owner_b, self.business_b)  # B's owner holds every permission

    def test_detail_and_actions_are_404(self):
        sale_detail = reverse("sales:sale-detail", args=[self.sale["id"]])
        customer_detail = reverse("sales:customer-detail", args=[self.customer.pk])
        cases = [
            ("get", sale_detail, {}),
            ("get", customer_detail, {}),
            ("patch", customer_detail, {"name": "pwned"}),
            ("delete", customer_detail, {}),
            ("post", reverse("sales:sale-payments", args=[self.sale["id"]]), {"amount_received": "100"}),
            ("post", reverse("sales:sale-void", args=[self.sale["id"]]), {"reason": "x"}),
        ]
        for method, url, body in cases:
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(self.client, method)(url, body, format="json").status_code, 404)
        self.assertEqual(Payment.all_objects.count(), 1)
        self.assertEqual(Sale.all_objects.get().status, "COMPLETED")
        self.assertEqual(Customer.all_objects.get().name, "A customer")

    def test_lists_and_summary_show_nothing_of_another_business(self):
        self.assertEqual(self.client.get(SALES_URL).data["count"], 0)
        # A's seller isn't a member here: refused like an unknown id.
        self.assertEqual(self.client.get(SALES_URL, {"sold_by": str(self.owner_a.pk)}).status_code, 400)
        self.assertEqual(self.client.get(SALES_URL, {"sold_by": str(self.owner_b.pk)}).status_code, 200)
        self.assertEqual(self.client.get(reverse("sales:customer-list")).data["count"], 0)
        summary = self.client.get(reverse("sales:summary")).data
        self.assertEqual(summary["sales_count"], 0)
        self.assertEqual(D(summary["outstanding_credit"]), D("0"))
        self.assertEqual(D(summary["cash_collected"]), D("0"))

    def test_foreign_ids_cannot_be_used(self):
        own = make_product(self.business_b, "B product")
        stock(self.business_b, own, 5, self.owner_b)

        foreign_product = self.sell([{"product": str(self.product.pk), "quantity": 1}])
        self.assertEqual(foreign_product.status_code, 400)
        self.assertIn("items", foreign_product.data)

        foreign_customer = self.sell(
            [{"product": str(own.pk), "quantity": 1}], amount_received="0", customer=str(self.customer.pk)
        )
        self.assertEqual(foreign_customer.status_code, 400)
        self.assertIn("customer", foreign_customer.data)

        self.assertEqual(Sale.all_objects.filter(business=self.business_b).count(), 0)
        self.assertEqual(self.product_stock(self.product), 9)
