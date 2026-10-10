"""FR-11 to FR-13: recording a cash sale."""

from unittest import mock

from django.urls import reverse

from accounts.models import User

from catalog.tests.helpers import days, make_member, make_product, stock
from core.tenancy import tenant_context
from inventory.models import StockMovement
from sales.models import Customer, Payment, Sale, SaleItem, SaleItemAllocation
from sales.services import create_sale

from .helpers import SALES_URL, D, SalesAPITestCase


class CreateSaleTests(SalesAPITestCase):
    def test_cash_sale_with_change(self):
        response = self.sell(
            [{"product": str(self.product.pk), "quantity": 2, "discount": "1000"}],
            amount_received="25000",
        )
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data
        self.assertEqual(data["receipt_number"], "S-000001")
        self.assertEqual(D(data["subtotal"]), D("24000"))
        self.assertEqual(D(data["discount_total"]), D("1000"))
        self.assertEqual(D(data["total"]), D("23000"))
        self.assertEqual(D(data["cost_total"]), D("16000"))
        self.assertEqual(D(data["gross_profit"]), D("7000"))
        self.assertEqual(D(data["amount_paid"]), D("23000"))
        self.assertEqual(D(data["balance"]), D("0"))
        self.assertEqual(data["payment_status"], "PAID")
        payment = data["payments"][0]
        self.assertEqual(D(payment["amount_received"]), D("25000"))
        self.assertEqual(D(payment["change_given"]), D("2000"))
        self.assertEqual(self.product_stock(self.product), 8)
        self.assertEqual(data["items"][0]["allocations"][0]["quantity"], 2)

    def test_receipt_numbers_are_sequential_per_business(self):
        self.sell()
        self.assertEqual(self.sell().data["receipt_number"], "S-000002")
        other = make_product(self.business_b, "B product")
        stock(self.business_b, other, 3, self.owner_b)
        self.as_user(self.owner_b, self.business_b)
        response = self.sell([{"product": str(other.pk), "quantity": 1}])
        self.assertEqual(response.data["receipt_number"], "S-000001")

    def test_items_snapshot_price_and_cost(self):
        sale_id = self.sell().data["id"]
        with tenant_context(self.business_a):
            self.product.selling_price = D("50000")
            self.product.cost_price = D("1")
            self.product.save()
        data = self.client.get(reverse("sales:sale-detail", args=[sale_id])).data
        self.assertEqual(D(data["items"][0]["unit_price"]), D("12000"))
        self.assertEqual(D(data["items"][0]["unit_cost"]), D("8000"))
        self.assertEqual(D(data["gross_profit"]), D("4000"))

    def test_client_cannot_set_price_or_cost(self):
        response = self.sell(
            [{"product": str(self.product.pk), "quantity": 1, "unit_price": "1", "unit_cost": "99999"}]
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(D(response.data["total"]), D("12000"))
        self.assertEqual(D(response.data["cost_total"]), D("8000"))

    def test_fefo_takes_earliest_expiry_first_and_skips_expired(self):
        expired = stock(self.business_a, self.product, 5, self.owner_a, batch_number="OLD", expiry_date=days(-1))
        soon = stock(self.business_a, self.product, 3, self.owner_a, batch_number="SOON", expiry_date=days(10))
        response = self.sell([{"product": str(self.product.pk), "quantity": 5}], amount_received="60000")
        self.assertEqual(response.status_code, 201, response.data)
        allocations = response.data["items"][0]["allocations"]
        self.assertEqual(
            [(a["batch_number"], a["quantity"]) for a in allocations], [("SOON", 3), ("B1", 2)]
        )
        self.assertEqual(self.batch_stock(soon), 0)
        self.assertEqual(self.batch_stock(self.batch), 8)
        self.assertEqual(self.batch_stock(expired), 5)

    def test_insufficient_stock_is_refused_and_nothing_is_written(self):
        stock(self.business_a, self.product, 4, self.owner_a, batch_number="OLD", expiry_date=days(-3))
        response = self.sell([{"product": str(self.product.pk), "quantity": 11}], amount_received="200000")
        self.assertEqual(response.status_code, 400)
        self.assertIn("only 10 available", response.data["items"][0])
        self.assertEqual(Sale.all_objects.count(), 0)
        self.assertEqual(StockMovement.all_objects.filter(movement_type="SALE").count(), 0)
        self.assertEqual(self.product_stock(self.product), 14)

    def test_line_validation(self):
        archived = make_product(self.business_a, "Old cream", is_active=False)
        stock(self.business_a, archived, 2, self.owner_a)
        line = {"product": str(self.product.pk), "quantity": 1}
        cases = [
            ([], "items"),
            ([{**line, "quantity": 0}], "items"),
            ([{**line, "discount": "12000.01"}], "items"),
            ([{**line, "discount": "-1"}], "items"),
            ([line, line], "items"),
            ([{"product": str(archived.pk), "quantity": 1}], "items"),
        ]
        for items, field in cases:
            with self.subTest(items=items):
                response = self.sell(items, amount_received="100000")
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)
        self.assertEqual(Sale.all_objects.count(), 0)

    def test_full_discount_is_allowed(self):
        response = self.sell(
            [{"product": str(self.product.pk), "quantity": 1, "discount": "12000"}], amount_received="0"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["payment_status"], "PAID")
        self.assertEqual(response.data["payments"], [])

    def test_failure_midway_rolls_everything_back(self):
        """FR-12: a failure after items and stock movements were written
        leaves no sale, item, allocation, movement, payment or customer."""
        with tenant_context(self.business_a):
            with mock.patch.object(Payment.objects, "create", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    create_sale(
                        user=self.owner_a,
                        lines=[{"product": self.product, "quantity": 3}],
                        new_customer={"name": "Asha", "phone": "0700"},
                        amount_received=D("1000"),
                    )
        for model in (Sale, SaleItem, SaleItemAllocation, Payment, Customer):
            with self.subTest(model=model.__name__):
                self.assertEqual(model.all_objects.count(), 0)
        self.assertEqual(StockMovement.all_objects.filter(movement_type="SALE").count(), 0)
        self.assertEqual(self.product_stock(self.product), 10)


class CreditSaleTests(SalesAPITestCase):
    def test_short_cash_needs_a_customer(self):
        response = self.sell(amount_received="5000")
        self.assertEqual(response.status_code, 400)
        self.assertIn("customer", response.data)
        self.assertEqual(Sale.all_objects.count(), 0)
        self.assertEqual(self.product_stock(self.product), 10)

    def test_partial_payment_with_new_customer(self):
        response = self.sell(amount_received="5000", new_customer={"name": "Mama Asha", "phone": "0712000000"})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["payment_status"], "PARTIAL")
        self.assertEqual(D(response.data["amount_paid"]), D("5000"))
        self.assertEqual(D(response.data["balance"]), D("7000"))
        self.assertEqual(response.data["customer_name"], "Mama Asha")

        customer = self.client.get(reverse("sales:customer-detail", args=[response.data["customer"]])).data
        self.assertEqual(D(customer["balance"]), D("7000"))
        self.assertEqual(D(customer["total_bought"]), D("12000"))

    def test_nothing_paid_with_existing_customer(self):
        with tenant_context(self.business_a):
            customer = Customer.objects.create(name="Juma")
        response = self.sell(amount_received="0", customer=str(customer.pk))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["payment_status"], "UNPAID")
        self.assertEqual(response.data["payments"], [])

    def test_new_customer_phone_must_be_unique(self):
        with tenant_context(self.business_a):
            Customer.objects.create(name="Juma", phone="0712")
        response = self.sell(amount_received="0", new_customer={"name": "Other", "phone": "0712"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("new_customer", response.data)

    def test_customer_and_new_customer_together_is_refused(self):
        with tenant_context(self.business_a):
            customer = Customer.objects.create(name="Juma")
        response = self.sell(amount_received="0", customer=str(customer.pk), new_customer={"name": "X"})
        self.assertEqual(response.status_code, 400)

    def test_filters(self):
        self.sell()
        self.sell(amount_received="0", new_customer={"name": "Asha"})
        self.assertEqual(self.client.get(SALES_URL, {"payment_status": "UNPAID"}).data["count"], 1)
        self.assertEqual(self.client.get(SALES_URL, {"payment_status": "PAID"}).data["count"], 1)
        self.assertEqual(self.client.get(SALES_URL, {"receipt": "S-000002"}).data["count"], 1)
        self.assertEqual(self.client.get(SALES_URL, {"search": "asha"}).data["count"], 1)
        self.assertEqual(self.client.get(SALES_URL, {"date_from": days(1).isoformat()}).data["count"], 0)
        debtors = self.client.get(reverse("sales:customer-list"), {"has_balance": "true"}).data
        self.assertEqual([c["name"] for c in debtors["results"]], ["Asha"])


class SalePermissionTests(SalesAPITestCase):
    def test_role_without_sales_permissions_gets_403(self):
        cashier = make_member(self.business_a, "nobody@example.com", "Trainee")
        self.as_user(cashier, self.business_a)
        self.assertEqual(self.client.get(SALES_URL).status_code, 403)
        self.assertEqual(self.sell().status_code, 403)
        self.assertEqual(self.client.get(reverse("sales:summary")).status_code, 403)
        self.assertEqual(self.client.get(reverse("sales:customer-list")).status_code, 403)
        self.assertEqual(Sale.all_objects.count(), 0)

    def test_admin_can_sell_but_not_delete_customers(self):
        self.as_user(self.admin_a, self.business_a)
        self.assertEqual(self.sell().status_code, 201)
        with tenant_context(self.business_a):
            customer = Customer.objects.create(name="Juma")
        url = reverse("sales:customer-detail", args=[customer.pk])
        self.assertEqual(self.client.delete(url).status_code, 403)

    def test_sales_cannot_be_edited_or_deleted(self):
        sale_id = self.sell().data["id"]
        url = reverse("sales:sale-detail", args=[sale_id])
        # Refused by the permission layer (no PATCH/DELETE grant) before routing.
        self.assertIn(self.client.patch(url, {"total": "1"}, format="json").status_code, (403, 405))
        self.assertIn(self.client.delete(url).status_code, (403, 405))
        self.assertEqual(Sale.all_objects.get().total, D("12000"))


class CustomerTests(SalesAPITestCase):
    url = reverse("sales:customer-list")

    def test_crud_and_delete_rules(self):
        created = self.client.post(self.url, {"name": "Neema", "phone": "0755"}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(D(created.data["balance"]), D("0"))
        detail = reverse("sales:customer-detail", args=[created.data["id"]])
        self.assertEqual(self.client.patch(detail, {"notes": "VIP"}, format="json").status_code, 200)

        duplicate = self.client.post(self.url, {"name": "Other", "phone": "0755"}, format="json")
        self.assertEqual(duplicate.status_code, 400)

        self.sell(amount_received="0", customer=created.data["id"])
        self.assertEqual(self.client.delete(detail).status_code, 409)

        unused = self.client.post(self.url, {"name": "Gone"}, format="json").data
        self.assertEqual(self.client.delete(reverse("sales:customer-detail", args=[unused["id"]])).status_code, 204)


class AdminTests(SalesAPITestCase):
    def test_sale_admin_page_opens_without_a_tenant(self):
        sale_id = self.sell().data["id"]
        staff = User.objects.create_superuser(email="root@example.com", password="Str0ng-Passw0rd!")
        self.client.credentials()
        self.client.force_login(staff)
        response = self.client.get(reverse("admin:sales_sale_change", args=[sale_id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shea Butter")
