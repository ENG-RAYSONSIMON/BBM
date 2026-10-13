import io
import os
import shutil
import tempfile
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image

from accounts.models import Permission, Role, RolePermission
from catalog.tests.helpers import TenantAPITestCase, days, make_member, make_product, stock, today
from core.tenancy import tenant_context
from expenses.models import DEFAULT_CATEGORIES, Expense, ExpenseCategory

MEDIA = tempfile.mkdtemp(prefix="bbm-test-receipts-")
EXPENSES_URL = reverse("expenses:expense-list")
CATEGORIES_URL = reverse("expenses:category-list")
SUMMARY_URL = reverse("expenses:summary")


def D(value):
    return Decimal(str(value))


def png_file(name="receipt.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def pdf_file(name="receipt.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\n%%EOF\n", content_type="application/pdf")


def receipt_url(expense_id):
    return reverse("expenses:expense-receipt", args=[expense_id])


class ExpensesAPITestCase(TenantAPITestCase):
    def setUp(self):
        super().setUp()
        with tenant_context(self.business_a):
            self.rent = ExpenseCategory.objects.get(name="Rent")
            self.transport = ExpenseCategory.objects.get(name="Transport")
        self.as_user(self.owner_a, self.business_a)

    def add(self, amount="50000", category=None, expense_date=None, **extra):
        body = {
            "category": str((category or self.rent).pk),
            "amount": amount,
            "description": "Shop rent",
            **extra,
        }
        if expense_date:
            body["expense_date"] = expense_date.isoformat()
        return self.client.post(EXPENSES_URL, body, format="json")


class CategoryTests(ExpensesAPITestCase):
    def test_new_businesses_get_the_default_categories(self):
        for business in (self.business_a, self.business_b):
            with tenant_context(business):
                names = set(ExpenseCategory.objects.values_list("name", flat=True))
            self.assertEqual(names, set(DEFAULT_CATEGORIES))

    def test_crud_and_delete_rules(self):
        created = self.client.post(CATEGORIES_URL, {"name": "Packaging"}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(self.client.post(CATEGORIES_URL, {"name": "packaging"}, format="json").status_code, 400)
        detail = reverse("expenses:category-detail", args=[created.data["id"]])
        self.assertEqual(self.client.patch(detail, {"description": "Bags"}, format="json").status_code, 200)
        self.assertEqual(self.client.delete(detail).status_code, 204)

        self.add()
        in_use = self.client.delete(reverse("expenses:category-detail", args=[self.rent.pk]))
        self.assertEqual(in_use.status_code, 409)


class ExpenseTests(ExpensesAPITestCase):
    def test_record_and_edit(self):
        response = self.add(paid_to="Landlord")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["category_name"], "Rent")
        self.assertEqual(response.data["expense_date"], today().isoformat())
        self.assertEqual(response.data["method"], "CASH")
        self.assertFalse(response.data["has_receipt"])
        self.assertEqual(response.data["recorded_by"], self.owner_a.pk)

        detail = reverse("expenses:expense-detail", args=[response.data["id"]])
        edited = self.client.patch(detail, {"amount": "45000", "category": str(self.transport.pk)}, format="json")
        self.assertEqual(edited.status_code, 200, edited.data)
        self.assertEqual(D(edited.data["amount"]), D("45000"))
        self.assertEqual(edited.data["category_name"], "Transport")

    def test_amount_must_be_positive(self):
        for amount in ("0", "-5", "abc"):
            with self.subTest(amount):
                self.assertEqual(self.add(amount=amount).status_code, 400)
        self.assertEqual(Expense.all_objects.count(), 0)

    def test_filters_and_search(self):
        self.add(expense_date=days(-3))
        self.add(amount="8000", category=self.transport, description="Boda to supplier")
        cases = {
            "category": ({"category": str(self.transport.pk)}, 1),
            "date range": ({"date_from": days(-4).isoformat(), "date_to": days(-2).isoformat()}, 1),
            "search": ({"search": "boda"}, 1),
            "all": ({}, 2),
        }
        for label, (params, count) in cases.items():
            with self.subTest(label):
                self.assertEqual(self.client.get(EXPENSES_URL, params).data["count"], count)

    def test_summary_by_category(self):
        self.add("50000")
        self.add("8000", category=self.transport)
        self.add("2000", category=self.transport)
        self.add("99999", expense_date=days(-1))
        response = self.client.get(SUMMARY_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(D(response.data["total"]), D("60000"))
        self.assertEqual(response.data["count"], 3)
        rows = [(row["category_name"], D(row["total"]), row["count"]) for row in response.data["by_category"]]
        self.assertEqual(rows, [("Rent", D("50000"), 1), ("Transport", D("10000"), 2)])

        week = self.client.get(SUMMARY_URL, {"date_from": days(-6).isoformat(), "date_to": today().isoformat()})
        self.assertEqual(D(week.data["total"]), D("159999"))
        self.assertEqual(self.client.get(SUMMARY_URL, {"date_from": "nope"}).status_code, 400)
        backwards = {"date_from": today().isoformat(), "date_to": days(-1).isoformat()}
        self.assertEqual(self.client.get(SUMMARY_URL, backwards).status_code, 400)

    def test_admin_can_record_but_not_delete(self):
        self.as_user(self.admin_a, self.business_a)
        created = self.add()
        self.assertEqual(created.status_code, 201)
        detail = reverse("expenses:expense-detail", args=[created.data["id"]])
        self.assertEqual(self.client.patch(detail, {"amount": "1"}, format="json").status_code, 200)
        self.assertEqual(self.client.delete(detail).status_code, 403)
        category = reverse("expenses:category-detail", args=[self.transport.pk])
        self.assertEqual(self.client.delete(category).status_code, 403)
        self.as_user(self.owner_a, self.business_a)
        self.assertEqual(self.client.delete(detail).status_code, 204)

    def test_role_without_expense_permissions_gets_403(self):
        trainee = make_member(self.business_a, "nobody@example.com", "Trainee")
        self.as_user(trainee, self.business_a)
        for url in (EXPENSES_URL, CATEGORIES_URL, SUMMARY_URL):
            with self.subTest(url):
                self.assertEqual(self.client.get(url).status_code, 403)
        self.assertEqual(self.add().status_code, 403)


@override_settings(PRIVATE_MEDIA_ROOT=MEDIA)
class ReceiptTests(ExpensesAPITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.expense_id = self.add().data["id"]

    def upload(self, file):
        return self.client.put(receipt_url(self.expense_id), {"receipt": file}, format="multipart")

    def test_photo_and_pdf_receipts(self):
        for file, content_type in ((png_file(), "image/png"), (pdf_file(), "application/pdf")):
            with self.subTest(content_type):
                # The replaced file is deleted once the change commits.
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.upload(file)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertTrue(response.data["has_receipt"])
                download = self.client.get(receipt_url(self.expense_id))
                self.assertEqual(download.status_code, 200)
                self.assertEqual(download["Content-Type"], content_type)
                self.assertEqual(download["X-Content-Type-Options"], "nosniff")
                self.assertEqual(download["Content-Security-Policy"], "sandbox")
                self.assertTrue(download["Content-Disposition"].startswith("attachment;"))
                # Reading the stream lets the test client close it safely.
                file.seek(0)
                self.assertEqual(b"".join(download.streaming_content), file.read())
        # Replacing removed the PNG; only the PDF is stored.
        name = Expense.all_objects.get().receipt.name
        self.assertTrue(name.startswith(f"receipts/{self.business_a.pk}/"))
        self.assertTrue(name.endswith(".pdf"))
        self.assertEqual(len(list(os.scandir(f"{MEDIA}/receipts/{self.business_a.pk}"))), 1)

    def test_receipts_are_stored_outside_public_media(self):
        public = tempfile.mkdtemp(prefix="bbm-test-public-")
        try:
            with override_settings(MEDIA_ROOT=public):
                self.upload(pdf_file())
            self.assertEqual(os.listdir(public), [])
            receipt = Expense.all_objects.get().receipt
            self.assertTrue(receipt.path.startswith(MEDIA))
            with self.assertRaises(ValueError):
                receipt.url
        finally:
            shutil.rmtree(public, ignore_errors=True)

    def test_bad_files_are_refused(self):
        cases = {
            "fake pdf": SimpleUploadedFile("r.pdf", b"PDF-1.4 not really", content_type="application/pdf"),
            "text": SimpleUploadedFile("r.txt", b"hello", content_type="text/plain"),
            "php as png": SimpleUploadedFile("r.png", b"<?php echo 1; ?>", content_type="image/png"),
        }
        for label, file in cases.items():
            with self.subTest(label):
                response = self.upload(file)
                self.assertEqual(response.status_code, 400)
                self.assertIn("PDF", str(response.data["receipt"]))
        self.assertFalse(Expense.all_objects.get().receipt)

    @override_settings(EXPENSE_RECEIPT_MAX_BYTES=10)
    def test_oversize_file_is_refused(self):
        response = self.upload(pdf_file())
        self.assertEqual(response.status_code, 400)
        self.assertIn("too large", str(response.data["receipt"]))

    def test_remove_and_missing_receipt(self):
        self.assertEqual(self.client.get(receipt_url(self.expense_id)).status_code, 404)
        self.upload(png_file())
        removed = self.client.delete(receipt_url(self.expense_id))
        self.assertEqual(removed.status_code, 200)
        self.assertFalse(removed.data["has_receipt"])
        self.assertEqual(self.client.get(receipt_url(self.expense_id)).status_code, 404)

    def test_viewer_without_manage_cannot_upload(self):
        viewer = make_member(self.business_a, "viewer@example.com", "Viewer")
        with tenant_context(self.business_a):
            role = Role.objects.get(name="Viewer")
            RolePermission.objects.create(role=role, permission=Permission.objects.get(codename="expenses.view"))
        self.as_user(viewer, self.business_a)
        self.assertEqual(self.upload(png_file()).status_code, 403)
        self.assertEqual(self.client.get(receipt_url(self.expense_id)).status_code, 404)  # allowed, none yet


class NetProfitTests(ExpensesAPITestCase):
    """FR-16: net profit = gross profit − expenses dated in the range."""

    def setUp(self):
        super().setUp()
        product = make_product(self.business_a)  # sells 12,000, costs 8,000
        stock(self.business_a, product, 5, self.owner_a)
        sale = {"items": [{"product": str(product.pk), "quantity": 2}], "amount_received": "24000"}
        self.client.post(reverse("sales:sale-list"), sale, format="json")  # gross profit 8,000
        self.add("3000")
        self.add("10000", expense_date=days(-1))

    def test_summary_includes_expenses_and_net_profit(self):
        today_summary = self.client.get(reverse("sales:summary")).data
        self.assertEqual(D(today_summary["gross_profit"]), D("8000"))
        self.assertEqual(D(today_summary["expenses"]), D("3000"))
        self.assertEqual(D(today_summary["net_profit"]), D("5000"))

        two_days = self.client.get(
            reverse("sales:summary"), {"date_from": days(-1).isoformat(), "date_to": today().isoformat()}
        ).data
        self.assertEqual(D(two_days["net_profit"]), D("-5000"))

    def test_expense_figures_need_the_expenses_permission(self):
        seller = make_member(self.business_a, "seller@example.com", "Seller")
        with tenant_context(self.business_a):
            role = Role.objects.get(name="Seller")
            RolePermission.objects.create(role=role, permission=Permission.objects.get(codename="sales.view"))
        self.as_user(seller, self.business_a)
        summary = self.client.get(reverse("sales:summary")).data
        self.assertEqual(D(summary["gross_profit"]), D("8000"))
        self.assertIsNone(summary["expenses"])
        self.assertIsNone(summary["net_profit"])
