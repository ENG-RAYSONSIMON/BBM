"""Shared setup for catalog and inventory tests."""

from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Role, User, UserRole
from accounts.services import register_owner
from accounts.tokens import tokens_for
from catalog.models import Product, ProductBatch
from core.tenancy import tenant_context
from inventory.models import StockMovement
from inventory.services import record_movement, resolve_batch

PASSWORD = "Str0ng-Passw0rd!"


def today():
    return timezone.localdate()


def days(n):
    return today() + timedelta(days=n)


def make_owner(email, business_name):
    return register_owner(email=email, password=PASSWORD, business_name=business_name)


def make_member(business, email, role_name):
    user = User.objects.create_user(email=email, password=PASSWORD)
    with tenant_context(business):
        role, _ = Role.objects.get_or_create(name=role_name)
        UserRole.objects.create(user=user, role=role)
    return user


def make_product(business, name="Shea Butter", **fields):
    defaults = {"selling_price": Decimal("12000"), "cost_price": Decimal("8000")}
    with tenant_context(business):
        return Product.objects.create(name=name, **{**defaults, **fields})


def stock(
    business,
    product,
    quantity,
    user,
    *,
    batch_number="B1",
    expiry_date=None,
    movement_type=StockMovement.Type.ADJUSTMENT,
):
    """Record a movement directly through the service. Returns the batch."""
    with tenant_context(business):
        is_new = not ProductBatch.objects.filter(product=product, batch_number=batch_number).exists()
        if product.tracks_expiry and expiry_date is None and is_new:
            expiry_date = days(365)
        batch = resolve_batch(product, batch_number=batch_number, expiry_date=expiry_date)
        record_movement(
            product=product,
            batch=batch,
            movement_type=movement_type,
            quantity=quantity,
            user=user,
            reason="test",
        )
        return batch


class TenantAPITestCase(APITestCase):
    """Two businesses: A (owner_a, admin_a) and B (owner_b)."""

    def setUp(self):
        cache.clear()
        self.owner_a, self.business_a = make_owner("a@example.com", "Shop A")
        self.admin_a = make_member(self.business_a, "admin-a@example.com", Role.ADMIN)
        self.owner_b, self.business_b = make_owner("b@example.com", "Shop B")

    def as_user(self, user, business):
        access = tokens_for(user, business)["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
