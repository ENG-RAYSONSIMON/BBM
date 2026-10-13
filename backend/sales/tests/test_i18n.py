"""Server messages follow Accept-Language: Kiswahili for "sw", English
otherwise (locale/sw/LC_MESSAGES/django.po)."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import translation

from catalog.tests.helpers import make_member
from core.tenancy import tenant_context
from expenses.models import Expense, ExpenseCategory

from .helpers import SalesAPITestCase

PO_FILE = Path(settings.BASE_DIR) / "locale" / "sw" / "LC_MESSAGES" / "django.po"


class SwahiliMessagesTests(SalesAPITestCase):
    def sw(self, method, url, body=None):
        return getattr(self.client, method)(url, body or {}, format="json", HTTP_ACCEPT_LANGUAGE="sw")

    def test_sale_shortage_in_swahili(self):
        items = [{"product": str(self.product.pk), "quantity": 50}]
        response = self.sw("post", reverse("sales:sale-list"), {"items": items, "amount_received": "1000000"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["items"], ["Shea Butter: zimebaki 10 tu za kuuza."])

    def test_library_messages_in_swahili(self):
        missing = self.sw("post", reverse("sales:customer-list"))
        self.assertEqual(missing.data["name"], ["Sehemu hii ni lazima."])

        trainee = make_member(self.business_a, "trainee@example.com", "Trainee")
        self.as_user(trainee, self.business_a)
        self.assertEqual(self.sw("get", reverse("sales:sale-list")).data["detail"], "Huna ruhusa ya kufanya hivi.")

        self.client.credentials()
        self.assertEqual(self.sw("get", reverse("sales:sale-list")).data["detail"], "Tafadhali ingia kwanza.")

    def test_conflict_in_swahili(self):
        with tenant_context(self.business_a):
            rent = ExpenseCategory.objects.get(name="Rent")
            Expense.objects.create(category=rent, amount=1000, description="Rent", recorded_by=self.owner_a)
        response = self.sw("delete", reverse("expenses:category-detail", args=[rent.pk]))
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["detail"], "Aina hii ina matumizi, haiwezi kufutwa.")

    def test_english_without_the_header(self):
        response = self.client.post(reverse("sales:customer-list"), {}, format="json")
        self.assertEqual(response.data["name"], ["This field is required."])
        english = self.client.post(
            reverse("sales:customer-list"), {}, format="json", HTTP_ACCEPT_LANGUAGE="en"
        )
        self.assertEqual(english.data["name"], ["This field is required."])


class TranslationFileTests(SimpleTestCase):
    def test_every_message_is_translated(self):
        text = PO_FILE.read_text(encoding="utf-8")
        self.assertNotIn("#, fuzzy", text)
        # An empty msgstr not followed by a continuation line means untranslated
        # (the header is the one allowed exception).
        empty = re.findall(r'^msgstr(?:\[\d\])? ""\n(?!")', text, flags=re.M)
        self.assertEqual(empty, [])

    def test_compiled_file_is_current(self):
        """The .mo must be rebuilt after editing the .po (compilemessages)."""
        with translation.override("sw"):
            self.assertEqual(translation.gettext("This sale is already void."), "Mauzo haya yameshabatilishwa.")
            self.assertEqual(translation.gettext("Request was throttled."), "Umejaribu mara nyingi sana.")
