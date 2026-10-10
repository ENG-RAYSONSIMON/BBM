"""Paying off credit, voiding sales, and the FR-16/FR-17 summary."""

from django.db import transaction
from django.db.models import Sum
from django.urls import reverse

from catalog.tests.helpers import days, stock
from core.tenancy import tenant_context
from inventory.models import StockMovement
from sales.models import Payment, PaymentImmutable

from .helpers import D, SalesAPITestCase


class PaymentTests(SalesAPITestCase):
    def credit_sale(self, paid="2000"):
        response = self.sell(amount_received=paid, new_customer={"name": "Asha"})
        self.assertEqual(response.status_code, 201, response.data)
        return response.data["id"]

    def pay(self, sale_id, amount):
        return self.client.post(
            reverse("sales:sale-payments", args=[sale_id]), {"amount_received": amount}, format="json"
        )

    def detail(self, sale_id):
        return self.client.get(reverse("sales:sale-detail", args=[sale_id])).data

    def test_repayments_reduce_the_balance_and_overpayment_is_change(self):
        sale_id = self.credit_sale()
        first = self.pay(sale_id, "4000")
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(D(self.detail(sale_id)["balance"]), D("6000"))

        last = self.pay(sale_id, "10000")
        self.assertEqual(D(last.data["amount"]), D("6000"))
        self.assertEqual(D(last.data["change_given"]), D("4000"))
        sale = self.detail(sale_id)
        self.assertEqual(sale["payment_status"], "PAID")
        self.assertEqual(len(sale["payments"]), 3)

    def test_payment_refused_when_nothing_owed_or_amount_zero(self):
        paid_sale = self.sell().data["id"]
        self.assertEqual(self.pay(paid_sale, "1000").status_code, 400)
        sale_id = self.credit_sale()
        self.assertEqual(self.pay(sale_id, "0").status_code, 400)
        self.assertEqual(self.pay(sale_id, "-5").status_code, 400)

    def test_payments_are_append_only(self):
        self.sell()
        with tenant_context(self.business_a):
            payment = Payment.objects.get()
            payment.amount = D("1")
            with self.assertRaises(PaymentImmutable):
                payment.save()
            with self.assertRaises(PaymentImmutable), transaction.atomic():
                Payment.objects.all().delete()
        self.assertEqual(Payment.all_objects.count(), 1)


class VoidTests(SalesAPITestCase):
    def void(self, sale_id, reason="Wrong item"):
        return self.client.post(reverse("sales:sale-void", args=[sale_id]), {"reason": reason}, format="json")

    def test_void_returns_stock_to_its_batches_and_refunds_cash(self):
        soon = stock(self.business_a, self.product, 2, self.owner_a, batch_number="SOON", expiry_date=days(5))
        sale = self.sell(
            [{"product": str(self.product.pk), "quantity": 4}],
            amount_received="20000",
            new_customer={"name": "Asha"},
        ).data
        self.assertEqual(self.batch_stock(soon), 0)
        self.assertEqual(self.batch_stock(self.batch), 8)

        response = self.void(sale["id"])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "VOID")
        self.assertEqual(response.data["payment_status"], "VOID")
        self.assertEqual(response.data["void_reason"], "Wrong item")
        self.assertEqual(D(response.data["balance"]), D("0"))
        self.assertEqual(self.batch_stock(soon), 2)
        self.assertEqual(self.batch_stock(self.batch), 10)
        refund = response.data["payments"][-1]
        self.assertEqual((refund["kind"], D(refund["amount"])), ("REFUND", D("20000")))
        self.assertEqual(
            StockMovement.all_objects.filter(movement_type="RETURN").aggregate(n=Sum("quantity"))["n"], 4
        )
        customer = self.client.get(reverse("sales:customer-detail", args=[sale["customer"]])).data
        self.assertEqual(D(customer["balance"]), D("0"))

    def test_void_twice_or_without_reason_is_refused(self):
        sale_id = self.sell().data["id"]
        self.assertEqual(self.void(sale_id, reason="").status_code, 400)
        self.assertEqual(self.void(sale_id).status_code, 200)
        again = self.void(sale_id)
        self.assertEqual(again.status_code, 400)
        self.assertEqual(again.data["non_field_errors"], ["This sale is already void."])
        self.assertEqual(StockMovement.all_objects.filter(movement_type="RETURN").count(), 1)

    def test_void_unpaid_sale_writes_no_refund(self):
        sale_id = self.sell(amount_received="0", new_customer={"name": "Asha"}).data["id"]
        self.assertEqual(self.void(sale_id).status_code, 200)
        self.assertEqual(Payment.all_objects.count(), 0)

    def test_payment_on_void_sale_is_refused(self):
        sale_id = self.sell(amount_received="0", new_customer={"name": "Asha"}).data["id"]
        self.void(sale_id)
        response = self.client.post(
            reverse("sales:sale-payments", args=[sale_id]), {"amount_received": "100"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_admin_cannot_void(self):
        sale_id = self.sell().data["id"]
        self.as_user(self.admin_a, self.business_a)
        self.assertEqual(self.void(sale_id).status_code, 403)
        self.assertEqual(self.product_stock(self.product), 9)

    def test_stock_still_reconciles_with_the_ledger(self):
        """NFR-9 with sales and voids in the mix."""
        for _ in range(3):
            sale_id = self.sell([{"product": str(self.product.pk), "quantity": 2}], amount_received="24000").data["id"]
        self.void(sale_id)
        movements = StockMovement.all_objects.filter(product=self.product)
        self.assertEqual(movements.aggregate(n=Sum("quantity"))["n"], 6)
        self.assertEqual(self.product_stock(self.product), 6)


class SummaryTests(SalesAPITestCase):
    url = reverse("sales:summary")

    def test_today_totals(self):
        self.sell(
            [{"product": str(self.product.pk), "quantity": 2, "discount": "1000"}], amount_received="30000"
        )  # total 23,000, cost 16,000, paid 23,000
        credit = self.sell(amount_received="2000", new_customer={"name": "Asha"}).data  # 12,000 / 8,000, paid 2,000
        voided = self.sell(amount_received="12000").data
        self.client.post(reverse("sales:sale-void", args=[voided["id"]]), {"reason": "x"}, format="json")
        self.client.post(
            reverse("sales:sale-payments", args=[credit["id"]]), {"amount_received": "3000"}, format="json"
        )

        data = self.client.get(self.url).data
        self.assertEqual(data["sales_count"], 2)
        self.assertEqual(D(data["revenue"]), D("35000"))
        self.assertEqual(D(data["discounts"]), D("1000"))
        self.assertEqual(D(data["cogs"]), D("24000"))
        self.assertEqual(D(data["gross_profit"]), D("11000"))
        # 23,000 + 2,000 + 12,000 − 12,000 refund + 3,000
        self.assertEqual(D(data["cash_collected"]), D("28000"))
        self.assertEqual(D(data["outstanding_credit"]), D("7000"))

    def test_date_range_and_validation(self):
        self.sell()
        tomorrow = days(1).isoformat()
        data = self.client.get(self.url, {"date_from": tomorrow}).data
        self.assertEqual(data["sales_count"], 0)
        self.assertEqual(D(data["outstanding_credit"]), D("0"))
        self.assertEqual(self.client.get(self.url, {"date_from": "nope"}).status_code, 400)
        self.assertEqual(
            self.client.get(self.url, {"date_from": tomorrow, "date_to": days(0).isoformat()}).status_code, 400
        )
