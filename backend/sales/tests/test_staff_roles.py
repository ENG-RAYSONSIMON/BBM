"""Seller and Cashier: what each may do, own-sales visibility, and buying
cost and profit hidden without finance.view. The Cashier runs the money
path (stock, purchases, expenses) but never deletes or voids."""

from django.urls import reverse

from accounts.models import Role
from catalog.models import Supplier
from catalog.tests.helpers import days, make_member
from core.tenancy import tenant_context
from expenses.models import ExpenseCategory

from .helpers import SALES_URL, SalesAPITestCase

SUMMARY_URL = reverse("sales:summary")
PRODUCTS_URL = reverse("catalog:product-list")
SALE_COST_FIELDS = {"cost_total", "gross_profit"}
ITEM_COST_FIELDS = {"unit_cost", "line_cost"}


def detail_url(pk):
    return reverse("sales:sale-detail", args=[pk])


class StaffRoleTests(SalesAPITestCase):
    def setUp(self):
        super().setUp()
        self.seller = make_member(self.business_a, "seller@example.com", Role.SELLER)
        self.seller_2 = make_member(self.business_a, "seller2@example.com", Role.SELLER)
        self.cashier = make_member(self.business_a, "cashier@example.com", Role.CASHIER)

    def credit_sale_by(self, user):
        self.as_user(user, self.business_a)
        response = self.sell(amount_received="2000", new_customer={"name": "Neema"})
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_seller_sells_and_sees_only_their_own_sales(self):
        mine = self.credit_sale_by(self.seller)
        theirs = self.credit_sale_by(self.seller_2)

        self.as_user(self.seller, self.business_a)
        listed = self.client.get(SALES_URL).data
        self.assertEqual([s["id"] for s in listed["results"]], [mine["id"]])
        self.assertEqual(self.client.get(detail_url(mine["id"])).status_code, 200)
        self.assertEqual(self.client.get(detail_url(theirs["id"])).status_code, 404)

    def test_seller_cannot_take_repayments_see_totals_or_void(self):
        sale = self.credit_sale_by(self.seller)
        self.assertEqual(self.client.get(SUMMARY_URL).status_code, 403)
        payment = self.client.post(
            reverse("sales:sale-payments", args=[sale["id"]]), {"amount_received": "1000"}, format="json"
        )
        self.assertEqual(payment.status_code, 403)
        void = self.client.post(reverse("sales:sale-void", args=[sale["id"]]), {"reason": "x"}, format="json")
        self.assertEqual(void.status_code, 403)
        # Products are read-only for a seller.
        self.assertEqual(self.client.get(PRODUCTS_URL).status_code, 200)
        self.assertEqual(self.client.post(PRODUCTS_URL, {"name": "X"}, format="json").status_code, 403)

    def test_cashier_sees_all_sales_and_takes_repayments(self):
        sale = self.credit_sale_by(self.seller)
        self.as_user(self.cashier, self.business_a)
        self.assertEqual(self.client.get(SALES_URL).data["count"], 1)
        payment = self.client.post(
            reverse("sales:sale-payments", args=[sale["id"]]), {"amount_received": "1000"}, format="json"
        )
        self.assertEqual(payment.status_code, 201, payment.data)

        summary = self.client.get(SUMMARY_URL).data
        self.assertEqual(summary["revenue"], "12000.00")
        self.assertEqual(summary["cash_collected"], "3000.00")
        self.assertEqual(summary["gross_profit"], "4000.00")
        self.assertEqual(summary["net_profit"], "4000.00")  # no expenses yet

    def test_cost_and_profit_hidden_from_sellers(self):
        sale = self.credit_sale_by(self.seller)
        listed = self.client.get(SALES_URL).data["results"][0]
        self.assertFalse(SALE_COST_FIELDS & listed.keys())
        detail = self.client.get(detail_url(sale["id"])).data
        self.assertFalse(SALE_COST_FIELDS & detail.keys())
        self.assertFalse(ITEM_COST_FIELDS & detail["items"][0].keys())
        product = self.client.get(PRODUCTS_URL).data["results"][0]
        self.assertNotIn("cost_price", product)
        self.assertIn("selling_price", product)
        # The sale's own response, straight after selling, hides them too.
        self.assertFalse(SALE_COST_FIELDS & sale.keys())

    def test_owner_admin_and_cashier_see_cost_and_profit(self):
        sale = self.credit_sale_by(self.seller)
        for user in (self.owner_a, self.admin_a, self.cashier):
            self.as_user(user, self.business_a)
            with self.subTest(user=user.email):
                detail = self.client.get(detail_url(sale["id"])).data
                self.assertEqual(detail["gross_profit"], "4000.00")
                self.assertEqual(detail["items"][0]["unit_cost"], "8000.00")
                self.assertEqual(self.client.get(PRODUCTS_URL).data["results"][0]["cost_price"], "8000.00")
                self.assertEqual(self.client.get(SUMMARY_URL).data["gross_profit"], "4000.00")


class CashierRunsTheShopTests(SalesAPITestCase):
    """For an owner who is far away, the cashier keeps products, stock,
    purchases and expenses going, but never deletes, voids or reaches
    reports, settings or staff."""

    def setUp(self):
        super().setUp()
        self.cashier = make_member(self.business_a, "cashier@example.com", Role.CASHIER)
        with tenant_context(self.business_a):
            self.supplier = Supplier.objects.create(name="Dar Cosmetics")
            self.rent = ExpenseCategory.objects.get(name="Rent")
        self.as_user(self.cashier, self.business_a)

    def test_adds_products_stock_purchases_and_expenses(self):
        product = self.client.post(
            PRODUCTS_URL, {"name": "Rose Toner", "selling_price": "15000", "cost_price": "9000"}, format="json"
        )
        self.assertEqual(product.status_code, 201, product.data)
        self.assertEqual(product.data["cost_price"], "9000.00")
        pk = product.data["id"]

        opening = self.client.post(
            reverse("inventory:stock-movement-list"),
            {"product": pk, "movement_type": "ADJUSTMENT", "quantity": 5, "reason": "Opening stock",
             "batch_number": "RT-1", "expiry_date": days(300).isoformat()},
            format="json",
        )
        self.assertEqual(opening.status_code, 201, opening.data)

        purchase = self.client.post(
            reverse("purchases:purchase-list"),
            {"supplier": str(self.supplier.pk), "items": [
                {"product": pk, "quantity": 10, "unit_cost": "9500", "batch_number": "RT-2",
                 "expiry_date": days(400).isoformat()}]},
            format="json",
        )
        self.assertEqual(purchase.status_code, 201, purchase.data)
        received = self.client.post(reverse("purchases:purchase-receive", args=[purchase.data["id"]]))
        self.assertEqual(received.status_code, 200, received.data)
        detail = self.client.get(reverse("catalog:product-detail", args=[pk])).data
        self.assertEqual((detail["stock_on_hand"], detail["cost_price"]), (15, "9500.00"))

        expense = self.client.post(
            reverse("expenses:expense-list"),
            {"category": str(self.rent.pk), "amount": "50000", "description": "Shop rent"},
            format="json",
        )
        self.assertEqual(expense.status_code, 201, expense.data)

    def test_never_deletes_voids_or_reaches_owner_pages(self):
        sale = self.sell().data
        expense = self.client.post(
            reverse("expenses:expense-list"),
            {"category": str(self.rent.pk), "amount": "1000", "description": "Tea"},
            format="json",
        ).data
        refused = [
            self.client.delete(reverse("catalog:product-detail", args=[self.product.pk])),
            self.client.delete(reverse("catalog:supplier-detail", args=[self.supplier.pk])),
            self.client.delete(reverse("expenses:expense-detail", args=[expense["id"]])),
            self.client.delete(reverse("expenses:category-detail", args=[self.rent.pk])),
            self.client.post(reverse("sales:sale-void", args=[sale["id"]]), {"reason": "x"}, format="json"),
            self.client.get(reverse("reports:sales")),
            self.client.get(reverse("accounts:settings")),
            self.client.get(reverse("accounts:staff-list")),
            self.client.get(reverse("audit:audit-log-list")),
        ]
        self.assertEqual([r.status_code for r in refused], [403] * len(refused))

