from django.urls import reverse

from accounts.models import Permission, Role, RolePermission
from accounts.rbac import CATALOG_VIEW
from catalog.models import Category, Product
from core.tenancy import tenant_context

from .helpers import TenantAPITestCase, days, make_member, make_product, stock

CATEGORIES = reverse("catalog:category-list")
PRODUCTS = reverse("catalog:product-list")


def category_url(pk):
    return reverse("catalog:category-detail", args=[pk])


def product_url(pk):
    return reverse("catalog:product-detail", args=[pk])


class CategoryAPITests(TenantAPITestCase):
    def test_owner_can_create_list_update_and_delete(self):
        self.as_user(self.owner_a, self.business_a)

        created = self.client.post(CATEGORIES, {"name": "Skincare"}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        pk = created.data["id"]

        listed = self.client.get(CATEGORIES)
        self.assertEqual(listed.data["count"], 1)
        self.assertEqual(listed.data["results"][0]["name"], "Skincare")

        updated = self.client.patch(category_url(pk), {"name": "Skin care"}, format="json")
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(self.client.delete(category_url(pk)).status_code, 204)

    def test_duplicate_name_is_a_400_not_a_500(self):
        self.as_user(self.owner_a, self.business_a)
        self.client.post(CATEGORIES, {"name": "Skincare"}, format="json")

        response = self.client.post(CATEGORIES, {"name": "skincare"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)

    def test_same_name_allowed_in_another_business(self):
        self.as_user(self.owner_a, self.business_a)
        self.client.post(CATEGORIES, {"name": "Skincare"}, format="json")
        self.as_user(self.owner_b, self.business_b)
        self.assertEqual(self.client.post(CATEGORIES, {"name": "Skincare"}, format="json").status_code, 201)

    def test_admin_can_edit_but_not_delete(self):
        with tenant_context(self.business_a):
            category = Category.objects.create(name="Hair")
        self.as_user(self.admin_a, self.business_a)

        self.assertEqual(
            self.client.patch(category_url(category.pk), {"name": "Haircare"}, format="json").status_code, 200
        )
        self.assertEqual(self.client.delete(category_url(category.pk)).status_code, 403)

    def test_deleting_a_category_in_use_is_409(self):
        with tenant_context(self.business_a):
            category = Category.objects.create(name="Hair")
        make_product(self.business_a, category=category)
        self.as_user(self.owner_a, self.business_a)

        response = self.client.delete(category_url(category.pk))

        self.assertEqual(response.status_code, 409)
        self.assertIn("products", response.data["detail"])

    def test_role_without_catalog_grants_is_forbidden(self):
        cashier = make_member(self.business_a, "cashier@example.com", "Cashier")
        self.as_user(cashier, self.business_a)
        self.assertEqual(self.client.get(CATEGORIES).status_code, 403)

        with tenant_context(self.business_a):
            RolePermission.objects.create(
                role=Role.objects.get(name="Cashier"),
                permission=Permission.objects.get(codename=CATALOG_VIEW),
            )
        self.assertEqual(self.client.get(CATEGORIES).status_code, 200)
        self.assertEqual(self.client.post(CATEGORIES, {"name": "X"}, format="json").status_code, 403)


class ProductAPITests(TenantAPITestCase):
    def payload(self, **overrides):
        return {"name": "Rose Toner", "selling_price": "15000.00", "cost_price": "9000.00", **overrides}

    def test_create_returns_derived_stock_fields(self):
        self.as_user(self.owner_a, self.business_a)
        with tenant_context(self.business_a):
            category = Category.objects.create(name="Skincare")

        response = self.client.post(PRODUCTS, self.payload(category=str(category.pk)), format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["category_detail"], {"id": str(category.pk), "name": "Skincare"})
        self.assertEqual(response.data["stock_on_hand"], 0)
        self.assertEqual(response.data["stock_status"], "out")
        self.assertEqual(response.data["threshold"], 5)  # business default
        self.assertIsNone(response.data["nearest_expiry"])

    def test_stock_is_not_writable(self):
        self.as_user(self.owner_a, self.business_a)
        response = self.client.post(PRODUCTS, self.payload(stock_on_hand=500), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["stock_on_hand"], 0)

    def test_list_shows_stock_and_nearest_expiry_of_batches_with_stock(self):
        product = make_product(self.business_a)
        stock(self.business_a, product, 10, self.owner_a, batch_number="LATE", expiry_date=days(90))
        stock(self.business_a, product, 4, self.owner_a, batch_number="EARLY", expiry_date=days(10))
        stock(
            self.business_a, product, -4, self.owner_a,
            batch_number="EARLY", expiry_date=days(10), movement_type="DAMAGE",
        )
        self.as_user(self.owner_a, self.business_a)

        item = self.client.get(PRODUCTS).data["results"][0]

        self.assertEqual(item["stock_on_hand"], 10)
        self.assertEqual(item["nearest_expiry"], days(90).isoformat())  # EARLY is empty

    def test_filters_search_and_pagination(self):
        low = make_product(self.business_a, "Aloe Gel", sku="ALOE-1")
        plenty = make_product(self.business_a, "Body Lotion", reorder_level=2)
        make_product(self.business_a, "Archived", is_active=False)
        stock(self.business_a, low, 3, self.owner_a)
        stock(self.business_a, plenty, 50, self.owner_a)
        self.as_user(self.owner_a, self.business_a)

        def names(query):
            return [p["name"] for p in self.client.get(PRODUCTS, query).data["results"]]

        self.assertEqual(names({"stock_status": "low", "is_active": "true"}), ["Aloe Gel"])
        self.assertEqual(names({"stock_status": "in"}), ["Body Lotion"])
        self.assertEqual(names({"stock_status": "out"}), ["Archived"])
        self.assertEqual(names({"search": "aloe-1"}), ["Aloe Gel"])
        self.assertEqual(names({"is_active": "false"}), ["Archived"])

        page = self.client.get(PRODUCTS, {"page_size": 2}).data
        self.assertEqual(page["count"], 3)
        self.assertEqual(len(page["results"]), 2)
        self.assertIsNotNone(page["next"])

    def test_reorder_level_overrides_business_threshold(self):
        product = make_product(self.business_a, reorder_level=20)
        stock(self.business_a, product, 15, self.owner_a)
        self.as_user(self.owner_a, self.business_a)

        data = self.client.get(product_url(product.pk)).data

        self.assertEqual(data["threshold"], 20)
        self.assertEqual(data["stock_status"], "low")

    def test_duplicate_sku_is_400(self):
        make_product(self.business_a, sku="SKU-1")
        self.as_user(self.owner_a, self.business_a)
        response = self.client.post(PRODUCTS, self.payload(sku="sku-1"), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("sku", response.data)

    def test_negative_price_is_400(self):
        self.as_user(self.owner_a, self.business_a)
        response = self.client.post(PRODUCTS, self.payload(selling_price="-5"), format="json")
        self.assertEqual(response.status_code, 400)

    def test_product_with_stock_history_cannot_be_deleted_but_can_be_archived(self):
        product = make_product(self.business_a)
        stock(self.business_a, product, 5, self.owner_a)
        self.as_user(self.owner_a, self.business_a)

        self.assertEqual(self.client.delete(product_url(product.pk)).status_code, 409)
        archived = self.client.patch(product_url(product.pk), {"is_active": False}, format="json")
        self.assertEqual(archived.status_code, 200)
        self.assertFalse(archived.data["is_active"])

    def test_product_without_movements_can_be_deleted_with_its_empty_batches(self):
        product = make_product(self.business_a)
        with tenant_context(self.business_a):
            product.batches.create(batch_number="EMPTY", expiry_date=days(30))
        self.as_user(self.owner_a, self.business_a)

        self.assertEqual(self.client.delete(product_url(product.pk)).status_code, 204)
        self.assertFalse(Product.all_objects.filter(pk=product.pk).exists())

    def test_expiry_tracking_locked_once_batches_exist(self):
        product = make_product(self.business_a)
        stock(self.business_a, product, 5, self.owner_a)
        self.as_user(self.owner_a, self.business_a)

        response = self.client.patch(product_url(product.pk), {"tracks_expiry": False}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("tracks_expiry", response.data)
