import random

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.test import TestCase

from catalog.models import Product, ProductBatch
from catalog.tests.helpers import days, make_owner, make_product, stock
from core.tenancy import tenant_context
from inventory.models import LedgerImmutable, StockMovement
from inventory.services import (
    InsufficientStock,
    record_movement,
    resolve_batch,
    with_batch_stock,
    with_product_stock,
)


class LedgerTests(TestCase):
    def setUp(self):
        self.user, self.business = make_owner("a@example.com", "Shop A")
        self.product = make_product(self.business)

    def movement(self):
        stock(self.business, self.product, 5, self.user)
        return StockMovement.all_objects.get()

    def test_movements_cannot_be_edited(self):
        movement = self.movement()
        movement.quantity = 500
        with tenant_context(self.business), self.assertRaises(LedgerImmutable):
            movement.save()

    def test_movements_cannot_be_deleted_even_in_bulk(self):
        movement = self.movement()
        with tenant_context(self.business):
            with self.assertRaises(LedgerImmutable), transaction.atomic():
                movement.delete()
            with self.assertRaises(LedgerImmutable), transaction.atomic():
                StockMovement.objects.all().delete()
        self.assertEqual(StockMovement.all_objects.count(), 1)

    def test_database_enforces_quantity_signs(self):
        batch = stock(self.business, self.product, 5, self.user)
        with tenant_context(self.business):
            for movement_type, quantity in [("ADJUSTMENT", 0), ("DAMAGE", 3), ("SALE", 1), ("PURCHASE", -1)]:
                with self.subTest(movement_type=movement_type), self.assertRaises(IntegrityError), transaction.atomic():
                    StockMovement.objects.create(
                        product=self.product, batch=batch, movement_type=movement_type,
                        quantity=quantity, created_by=self.user,
                    )

    def test_batch_must_belong_to_the_movement_product(self):
        batch = stock(self.business, self.product, 5, self.user)
        other = make_product(self.business, "Other")
        with tenant_context(self.business), self.assertRaises(ValueError):
            StockMovement.objects.create(
                product=other, batch=batch, movement_type="ADJUSTMENT", quantity=1, created_by=self.user
            )

    def test_cannot_take_a_batch_below_zero(self):
        batch = stock(self.business, self.product, 5, self.user)
        with tenant_context(self.business):
            with self.assertRaises(InsufficientStock) as caught:
                record_movement(
                    product=self.product, batch=batch, movement_type="DAMAGE",
                    quantity=-6, user=self.user,
                )
        self.assertEqual(caught.exception.available, 5)
        self.assertEqual(StockMovement.all_objects.count(), 1)

    def test_stock_is_summed_per_batch_and_per_product(self):
        stock(self.business, self.product, 10, self.user, batch_number="A", expiry_date=days(30))
        stock(self.business, self.product, 7, self.user, batch_number="B", expiry_date=days(60))
        stock(self.business, self.product, -3, self.user, batch_number="A", movement_type="DAMAGE")
        with tenant_context(self.business):
            batches = {b.batch_number: b.stock_on_hand for b in with_batch_stock(ProductBatch.objects.all())}
            product = with_product_stock(Product.objects.all()).get()
        self.assertEqual(batches, {"A": 7, "B": 7})
        self.assertEqual(product.stock_on_hand, 14)

    def test_products_without_expiry_use_one_default_batch(self):
        product = make_product(self.business, "Comb", tracks_expiry=False)
        with tenant_context(self.business):
            first = resolve_batch(product)
            second = resolve_batch(product)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.batch_number, ProductBatch.DEFAULT_NUMBER)
        self.assertIsNone(first.expiry_date)

    def test_ledger_reconciles_after_many_random_movements(self):
        """NFR-9: reported stock always equals stock-in minus stock-out."""
        rng = random.Random(42)
        numbers = ["A", "B", "C"]
        for number in numbers:
            stock(self.business, self.product, 20, self.user, batch_number=number, expiry_date=days(30))
        with tenant_context(self.business):
            batches = list(ProductBatch.objects.all())
            for _ in range(60):
                batch = rng.choice(batches)
                quantity = rng.choice([-7, -3, -1, 1, 4, 9])
                try:
                    record_movement(
                        product=self.product, batch=batch, movement_type="ADJUSTMENT",
                        quantity=quantity, user=self.user,
                    )
                except InsufficientStock:
                    pass

            ins = StockMovement.objects.filter(quantity__gt=0).aggregate(t=Sum("quantity"))["t"]
            outs = StockMovement.objects.filter(quantity__lt=0).aggregate(t=Sum("quantity"))["t"] or 0
            product = with_product_stock(Product.objects.all()).get()
            per_batch = [b.stock_on_hand for b in with_batch_stock(ProductBatch.objects.all())]

        self.assertEqual(product.stock_on_hand, ins + outs)
        self.assertEqual(sum(per_batch), product.stock_on_hand)
        self.assertTrue(all(n >= 0 for n in per_batch))
