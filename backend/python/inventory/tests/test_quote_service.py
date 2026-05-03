from decimal import Decimal
from unittest import TestCase
from typing import Any, cast

from inventory.services.quote_service import QuoteService


class _NoopLogger:
    def debug(self, *_args, **_kwargs):
        return None


class _FakeProductService:
    def __init__(self, product: dict):
        self._product = product

    def get_product(self, _product_id):
        return dict(self._product)


class TestQuoteService(TestCase):

    def setUp(self):
        self.product = {
            "id": "65f1a2b3c4d5e6f7a8b9c0d1",
            "name": "Lego Classic Building Blocks",
            "category": "toys",
            "brand": "lego",
            "price": Decimal("20.00"),
            "quantity": 125,
            "minimum_stock_level": 20,
        }
        self.service = QuoteService(
            cast(Any, _FakeProductService(self.product)),
            cast(Any, _NoopLogger()),
        )

    def test_get_product_info_returns_quote_fields(self):
        info = self.service.get_product_info(self.product["id"])

        self.assertEqual(info["id"], self.product["id"])
        self.assertEqual(info["name"], self.product["name"])
        self.assertEqual(info["price"], 20.0)
        self.assertEqual(info["quantity"], 125)

    def test_check_inventory_derives_flags(self):
        inventory = self.service.check_inventory(self.product["id"])

        self.assertTrue(inventory["in_stock"])
        self.assertFalse(inventory["low_stock"])
        self.assertEqual(inventory["quantity_available"], 125)

    def test_calculate_quote_includes_tiered_discount(self):
        quote = self.service.calculate_quote(self.product["id"], 60)

        self.assertEqual(quote["tier_name"], "bulk_50_plus")
        self.assertEqual(quote["discount_percent"], 10.0)
        self.assertEqual(quote["subtotal"], 1200.0)
        self.assertEqual(quote["final_total"], 1080.0)
