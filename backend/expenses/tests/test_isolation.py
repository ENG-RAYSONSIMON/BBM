"""NFR-7: business B can't read, change, delete or reference business A's
expenses, categories and receipts."""

import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from core.tenancy import tenant_context
from expenses.models import Expense, ExpenseCategory

from .test_expenses import CATEGORIES_URL, EXPENSES_URL, SUMMARY_URL, D, ExpensesAPITestCase, receipt_url

MEDIA = tempfile.mkdtemp(prefix="bbm-test-receipts-iso-")


@override_settings(PRIVATE_MEDIA_ROOT=MEDIA)
class CrossTenantTests(ExpensesAPITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.expense_id = self.add().data["id"]
        pdf = SimpleUploadedFile("r.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")
        self.client.put(receipt_url(self.expense_id), {"receipt": pdf}, format="multipart")
        self.as_user(self.owner_b, self.business_b)  # B's owner holds every permission

    def test_detail_and_actions_are_404(self):
        expense = reverse("expenses:expense-detail", args=[self.expense_id])
        category = reverse("expenses:category-detail", args=[self.rent.pk])
        cases = [
            ("get", expense, {}),
            ("patch", expense, {"amount": "1"}),
            ("delete", expense, {}),
            ("get", category, {}),
            ("patch", category, {"name": "pwned"}),
            ("delete", category, {}),
            ("get", receipt_url(self.expense_id), {}),
            ("delete", receipt_url(self.expense_id), {}),
        ]
        upload = SimpleUploadedFile("x.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")
        put = self.client.put(receipt_url(self.expense_id), {"receipt": upload}, format="multipart")
        self.assertEqual(put.status_code, 404)
        for method, url, body in cases:
            with self.subTest(method=method, url=url):
                self.assertEqual(getattr(self.client, method)(url, body, format="json").status_code, 404)
        expense_row = Expense.all_objects.get()
        self.assertEqual(expense_row.amount, D("50000"))
        self.assertTrue(expense_row.receipt)
        self.assertEqual(ExpenseCategory.all_objects.get(pk=self.rent.pk).name, "Rent")

    def test_lists_and_summary_show_nothing_of_another_business(self):
        self.assertEqual(self.client.get(EXPENSES_URL).data["count"], 0)
        # B sees only its own default categories.
        names = [row["id"] for row in self.client.get(CATEGORIES_URL, {"page_size": 100}).data["results"]]
        self.assertNotIn(str(self.rent.pk), names)
        self.assertEqual(D(self.client.get(SUMMARY_URL).data["total"]), D("0"))
        self.assertEqual(D(self.client.get(reverse("sales:summary")).data["expenses"]), D("0"))

    def test_foreign_category_cannot_be_used(self):
        response = self.add()  # self.rent belongs to A
        self.assertEqual(response.status_code, 400)
        self.assertIn("category", response.data)
        with tenant_context(self.business_b):
            own = ExpenseCategory.objects.get(name="Rent")
        self.assertEqual(self.add(category=own).status_code, 201)
