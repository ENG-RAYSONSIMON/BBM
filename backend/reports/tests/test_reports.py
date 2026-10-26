"""FR-18 reports: figures by period from the sale snapshots, payments and
expenses; stock valuation and expiry from the ledger; CSV export that is
audit-logged; permissions and tenant isolation."""

import csv
import io
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role, RolePermission
from audit.models import AuditLog
from catalog.models import Product
from catalog.tests.helpers import days, make_member, make_product, stock, today
from core.tenancy import tenant_context
from expenses.models import Expense, ExpenseCategory
from reports.services import period_starts
from sales.models import Payment, Sale
from sales.tests.helpers import D, SalesAPITestCase


def url(kind, export=False):
    return reverse(f"reports:{kind}-export" if export else f"reports:{kind}")


class PeriodStartsTests(SimpleTestCase):
    def test_periods_cover_the_range_and_start_on_their_first_day(self):
        self.assertEqual(period_starts(date(2026, 10, 30), date(2026, 11, 1), "day"),
                         [date(2026, 10, 30), date(2026, 10, 31), date(2026, 11, 1)])
        # 2026-10-28 is a Wednesday: its week starts Monday the 26th.
        self.assertEqual(period_starts(date(2026, 10, 28), date(2026, 11, 3), "week"),
                         [date(2026, 10, 26), date(2026, 11, 2)])
        self.assertEqual(period_starts(date(2026, 11, 15), date(2027, 1, 2), "month"),
                         [date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1)])
        self.assertEqual(period_starts(date(2025, 6, 1), date(2026, 2, 1), "year"),
                         [date(2025, 1, 1), date(2026, 1, 1)])


class ReportsTestCase(SalesAPITestCase):
    """Shea Butter sells at 12,000 and cost 8,000 (10 in stock)."""

    def backdate(self, sale_id, n_days):
        when = timezone.now() - timedelta(days=n_days)
        Sale.all_objects.filter(pk=sale_id).update(created_at=when)
        Payment.all_objects.filter(sale_id=sale_id).update(created_at=when)

    def expense(self, amount, category="Rent", expense_date=None):
        with tenant_context(self.business_a):
            Expense.objects.create(
                category=ExpenseCategory.objects.get(name=category),
                amount=D(amount),
                description="test",
                expense_date=expense_date or today(),
                recorded_by=self.owner_a,
            )


class SalesAndProfitReportTests(ReportsTestCase):
    def setUp(self):
        super().setUp()
        self.sell()  # today: 12,000 revenue, 8,000 cost, paid
        self.sell(amount_received="0", new_customer={"name": "Neema"})  # today, on credit
        old = self.sell().data["id"]
        self.backdate(old, 3)
        voided = self.sell().data["id"]
        self.client.post(reverse("sales:sale-void", args=[voided]), {"reason": "Wrong"}, format="json")

    def test_daily_sales_rows_fill_empty_days_and_leave_out_voids(self):
        params = {"date_from": days(-6).isoformat(), "date_to": today().isoformat()}
        response = self.client.get(url("sales"), params)
        self.assertEqual(response.status_code, 200, response.data)
        rows = {row["period"]: row for row in response.data["rows"]}
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[today().isoformat()]["sales_count"], 2)
        self.assertEqual(D(rows[today().isoformat()]["revenue"]), D("24000"))
        self.assertEqual(D(rows[today().isoformat()]["gross_profit"]), D("8000"))
        # The voided sale's payment and refund cancel out; the credit sale paid nothing.
        self.assertEqual(D(rows[today().isoformat()]["cash_collected"]), D("12000"))
        self.assertEqual(rows[days(-3).isoformat()]["sales_count"], 1)
        self.assertEqual(rows[days(-1).isoformat()]["sales_count"], 0)

        totals = response.data["totals"]
        self.assertEqual(totals["sales_count"], 3)
        self.assertEqual(D(totals["revenue"]), D("36000"))
        self.assertEqual(D(totals["cogs"]), D("24000"))
        self.assertEqual(D(totals["cash_collected"]), D("24000"))
        self.assertEqual(response.data["period"], "day")

    def test_periods_follow_the_shop_time_zone(self):
        # 22:30 UTC is 01:30 the next day in Dar es Salaam (UTC+3).
        sale = self.sell().data["id"]
        local_day = days(-10)
        day_before = local_day - timedelta(days=1)
        utc_evening = datetime(day_before.year, day_before.month, day_before.day, 22, 30, tzinfo=dt_timezone.utc)
        Sale.all_objects.filter(pk=sale).update(created_at=utc_evening)
        params = {"date_from": days(-12).isoformat(), "date_to": days(-9).isoformat()}
        rows = {row["period"]: row["sales_count"] for row in self.client.get(url("sales"), params).data["rows"]}
        self.assertEqual(rows[local_day.isoformat()], 1)
        self.assertEqual(rows[(local_day - timedelta(days=1)).isoformat()], 0)

    def test_default_range_is_the_last_30_days(self):
        data = self.client.get(url("sales")).data
        self.assertEqual(data["date_to"], today().isoformat())
        self.assertEqual(data["date_from"], days(-29).isoformat())
        self.assertEqual(len(data["rows"]), 30)

    def test_monthly_profit_subtracts_expenses(self):
        self.expense("5000")
        self.expense("1000", expense_date=today().replace(day=1) - timedelta(days=1))  # last month
        params = {"period": "month", "date_from": today().replace(day=1).isoformat(), "date_to": today().isoformat()}
        data = self.client.get(url("profit"), params).data
        self.assertEqual(len(data["rows"]), 1)
        row = data["rows"][0]
        self.assertEqual(row["period"], today().replace(day=1).isoformat())
        self.assertEqual(D(row["expenses"]), D("5000"))
        # 3 sales this month unless the backdated one fell into last month.
        sales_this_month = 3 if days(-3).month == today().month else 2
        self.assertEqual(D(row["gross_profit"]), D("4000") * sales_this_month)
        self.assertEqual(D(row["net_profit"]), D("4000") * sales_this_month - D("5000"))

    def test_bad_parameters_are_400(self):
        cases = [
            {"period": "hour"},
            {"date_from": "nope"},
            {"date_from": today().isoformat(), "date_to": days(-1).isoformat()},
            {"period": "day", "date_from": days(-400).isoformat()},
            # Out-of-range dates and spans are refused, not crashed on.
            {"date_to": "9999-12-31"},
            {"period": "year", "date_to": "9999-12-31"},
            {"date_to": "0001-01-05"},
            {"period": "week", "date_from": "0001-01-01"},
            {"period": "month", "date_from": "2001-01-01"},
        ]
        for params in cases:
            with self.subTest(params):
                self.assertEqual(self.client.get(url("sales"), params).status_code, 400)
        long_range = {"period": "month", "date_from": days(-400).isoformat()}
        self.assertEqual(self.client.get(url("sales"), long_range).status_code, 200)


class ExpensesReportTests(ReportsTestCase):
    def test_rows_per_period_and_category(self):
        self.expense("50000")
        self.expense("2000", category="Transport")
        self.expense("3000", category="Transport")
        data = self.client.get(url("expenses"), {"date_from": today().isoformat()}).data
        self.assertEqual(
            [(row["category_name"], row["count"], D(row["total"])) for row in data["rows"]],
            [("Rent", 1, D("50000")), ("Transport", 2, D("5000"))],
        )
        self.assertEqual(data["totals"]["count"], 3)
        self.assertEqual(D(data["totals"]["total"]), D("55000"))


class StockReportsTests(ReportsTestCase):
    def test_stock_valuation_at_cost_and_selling_price(self):
        make_product(self.business_a, "Rose Water")  # no stock: left out
        data = self.client.get(url("stock-valuation")).data
        self.assertEqual([row["name"] for row in data["rows"]], ["Shea Butter"])
        row = data["rows"][0]
        self.assertEqual(row["stock_on_hand"], 10)
        self.assertEqual(D(row["cost_value"]), D("80000"))
        self.assertEqual(D(row["retail_value"]), D("120000"))
        self.assertEqual(data["totals"]["product_count"], 1)
        self.assertEqual(data["as_of"], today().isoformat())

    def test_expiry_lists_expired_and_soon_expiring_batches(self):
        stock(self.business_a, self.product, 2, self.owner_a, batch_number="OLD", expiry_date=days(-5))
        stock(self.business_a, self.product, 3, self.owner_a, batch_number="SOON", expiry_date=days(20))
        data = self.client.get(url("expiry")).data  # 60 days by default; B1 expires in 200
        self.assertEqual(
            [(row["batch_number"], row["status"], row["days_left"]) for row in data["rows"]],
            [("OLD", "expired", -5), ("SOON", "expiring", 20)],
        )
        self.assertEqual(D(data["totals"]["cost_value"]), D("40000"))
        self.assertEqual(D(data["totals"]["expired_value"]), D("16000"))
        self.assertEqual(len(self.client.get(url("expiry"), {"within_days": 365}).data["rows"]), 3)
        self.assertEqual(self.client.get(url("expiry"), {"within_days": 0}).status_code, 400)

    def test_expiry_includes_archived_products(self):
        rose = make_product(self.business_a, "Rose Water", is_active=False)
        stock(self.business_a, rose, 4, self.owner_a, batch_number="R1", expiry_date=days(-1))
        [row] = self.client.get(url("expiry")).data["rows"]
        self.assertEqual((row["name"], row["is_active"]), ("Rose Water", False))


class ExportTests(ReportsTestCase):
    def test_csv_matches_the_report_and_is_audit_logged(self):
        self.sell()
        params = {"date_from": days(-1).isoformat(), "date_to": today().isoformat()}
        response = self.client.get(url("sales", export=True), params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn(f'filename="bbm-sales-{days(-1).isoformat()}-{today().isoformat()}.csv"',
                      response["Content-Disposition"])
        text = response.content.decode("utf-8")
        self.assertTrue(text.startswith("﻿"))
        rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
        self.assertEqual(rows[0][:3], ["Period starting", "Number of sales", "Revenue (TZS)"])
        self.assertEqual(rows[2][:3], [today().isoformat(), "1", "12000.00"])

        [entry] = AuditLog.all_objects.filter(business=self.business_a, action=AuditLog.Action.EXPORT)
        self.assertEqual(entry.actor, self.owner_a)
        self.assertEqual(entry.target_label, "sales")
        self.assertEqual(entry.changes["rows"], 2)

    def test_every_report_exports(self):
        for kind in ("sales", "profit", "expenses", "stock-valuation", "expiry"):
            with self.subTest(kind):
                self.assertEqual(self.client.get(url(kind, export=True)).status_code, 200)
        self.assertEqual(AuditLog.all_objects.filter(action=AuditLog.Action.EXPORT).count(), 5)

    def test_formula_like_names_are_written_as_text(self):
        make_product(self.business_a, "=1+1", sku="@cmd")
        stock(self.business_a, Product.all_objects.get(name="=1+1"), 1, self.owner_a)
        text = self.client.get(url("stock-valuation", export=True)).content.decode("utf-8").lstrip("\ufeff")
        row = next(r for r in csv.reader(io.StringIO(text)) if r[0].endswith("=1+1"))
        self.assertEqual(row[:2], ["'=1+1", "'@cmd"])

    def test_negative_numbers_stay_numbers(self):
        self.sell()
        self.expense("50000")
        text = self.client.get(url("profit", export=True), {"date_from": today().isoformat()}).content.decode("utf-8")
        self.assertEqual(list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))[1][-1], "-46000.00")

    def test_headers_follow_the_language(self):
        response = self.client.get(url("stock-valuation", export=True), HTTP_ACCEPT_LANGUAGE="sw")
        header = next(csv.reader(io.StringIO(response.content.decode("utf-8").lstrip("﻿"))))
        self.assertEqual(header[0], "Bidhaa")

    def test_bad_parameters_are_400_and_not_logged(self):
        self.assertEqual(self.client.get(url("sales", export=True), {"period": "hour"}).status_code, 400)
        self.assertFalse(AuditLog.all_objects.filter(action=AuditLog.Action.EXPORT).exists())


class PermissionTests(ReportsTestCase):
    def test_admin_can_view_and_export(self):
        self.as_user(self.admin_a, self.business_a)
        self.assertEqual(self.client.get(url("profit")).status_code, 200)
        self.assertEqual(self.client.get(url("profit", export=True)).status_code, 200)

    def test_viewing_and_exporting_need_their_permissions(self):
        clerk = make_member(self.business_a, "clerk@example.com", "Clerk")
        with tenant_context(self.business_a):
            role = Role.objects.get(name="Clerk")
            RolePermission.objects.create(role=role, permission_id=self._perm("reports.view"))
        self.as_user(clerk, self.business_a)
        for kind in ("sales", "profit", "expenses", "stock-valuation", "expiry"):
            with self.subTest(kind):
                self.assertEqual(self.client.get(url(kind)).status_code, 200)
                self.assertEqual(self.client.get(url(kind, export=True)).status_code, 403)

        # Export alone isn't enough: downloading is viewing too.
        exporter = make_member(self.business_a, "exporter@example.com", "Exporter")
        with tenant_context(self.business_a):
            role = Role.objects.get(name="Exporter")
            RolePermission.objects.create(role=role, permission_id=self._perm("reports.export"))
        self.as_user(exporter, self.business_a)
        self.assertEqual(self.client.get(url("sales", export=True)).status_code, 403)

        nobody = make_member(self.business_a, "nobody@example.com", "Nobody")
        self.as_user(nobody, self.business_a)
        for kind in ("sales", "profit", "expenses", "stock-valuation", "expiry"):
            with self.subTest(kind):
                self.assertEqual(self.client.get(url(kind)).status_code, 403)

    def _perm(self, codename):
        from accounts.models import Permission

        return Permission.objects.get(codename=codename).pk


class IsolationTests(ReportsTestCase):
    def test_another_business_sees_none_of_it(self):
        self.sell()
        self.expense("5000")
        self.as_user(self.owner_b, self.business_b)
        self.assertEqual(self.client.get(url("sales")).data["totals"]["sales_count"], 0)
        self.assertEqual(D(self.client.get(url("profit")).data["totals"]["expenses"]), D("0"))
        self.assertEqual(self.client.get(url("expenses")).data["rows"], [])
        self.assertEqual(self.client.get(url("stock-valuation")).data["rows"], [])
        self.assertEqual(self.client.get(url("expiry"), {"within_days": 365}).data["rows"], [])
        csv_text = self.client.get(url("stock-valuation", export=True)).content.decode("utf-8")
        self.assertNotIn("Shea Butter", csv_text)
