from decimal import Decimal
from unittest import TestCase

from inventory.domain.exceptions import ValidationError
from inventory.domain.quote_pricing import calculate_quote_pricing


class TestQuotePricing(TestCase):

    def test_standard_tier_at_50_units(self):
        result = calculate_quote_pricing(Decimal("20"), 50)

        self.assertEqual(result.tier_name, "bulk_20_plus")
        self.assertEqual(result.discount_percent, Decimal("5"))
        self.assertEqual(result.subtotal, Decimal("1000.00"))
        self.assertEqual(result.discount_amount, Decimal("50.00"))
        self.assertEqual(result.final_total, Decimal("950.00"))

    def test_ten_percent_discount_above_50_units(self):
        result = calculate_quote_pricing(Decimal("20"), 51)

        self.assertEqual(result.tier_name, "bulk_50_plus")
        self.assertEqual(result.discount_percent, Decimal("10"))
        self.assertEqual(result.subtotal, Decimal("1020.00"))
        self.assertEqual(result.discount_amount, Decimal("102.00"))
        self.assertEqual(result.final_total, Decimal("918.00"))

    def test_fifteen_percent_discount_above_100_units(self):
        result = calculate_quote_pricing(Decimal("20"), 101)

        self.assertEqual(result.tier_name, "bulk_100_plus")
        self.assertEqual(result.discount_percent, Decimal("15"))
        self.assertEqual(result.subtotal, Decimal("2020.00"))
        self.assertEqual(result.discount_amount, Decimal("303.00"))
        self.assertEqual(result.final_total, Decimal("1717.00"))

    def test_zero_quantity_is_rejected(self):
        with self.assertRaises(ValidationError):
            calculate_quote_pricing(Decimal("20"), 0)
