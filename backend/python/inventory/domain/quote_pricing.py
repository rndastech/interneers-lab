from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from inventory.domain.exceptions import ValidationError
from inventory.domain.validators import validate_price, validate_quantity


CURRENCY_PRECISION = Decimal("0.01")
PERCENT_BASE = Decimal("100")


@dataclass(frozen=True)
class DiscountTier:
    min_quantity_exclusive: int
    discount_percent: Decimal
    tier_name: str
    description: str


# Rules are evaluated top-down. First match wins.
DISCOUNT_TIERS = (
    DiscountTier(
        min_quantity_exclusive=100,
        discount_percent=Decimal("15"),
        tier_name="bulk_100_plus",
        description="15% off for quantities over 100",
    ),
    DiscountTier(
        min_quantity_exclusive=50,
        discount_percent=Decimal("10"),
        tier_name="bulk_50_plus",
        description="10% off for quantities over 50",
    ),
    DiscountTier(
        min_quantity_exclusive=20,
        discount_percent=Decimal("5"),
        tier_name="bulk_20_plus",
        description="5% off for quantities over 20",
    ),
    DiscountTier(
        min_quantity_exclusive=0,
        discount_percent=Decimal("0"),
        tier_name="standard",
        description="No discount",
    ),
)


@dataclass(frozen=True)
class QuotePricingResult:
    unit_price: Decimal
    quantity: int
    tier_name: str
    discount_description: str
    discount_percent: Decimal
    subtotal: Decimal
    discount_amount: Decimal
    final_total: Decimal

    def to_serializable_dict(self) -> dict:
        """Convert Decimal fields for JSON-safe API responses."""
        return {
            "unit_price": float(self.unit_price),
            "quantity": self.quantity,
            "tier_name": self.tier_name,
            "discount_description": self.discount_description,
            "discount_percent": float(self.discount_percent),
            "subtotal": float(self.subtotal),
            "discount_amount": float(self.discount_amount),
            "final_total": float(self.final_total),
        }


def calculate_quote_pricing(raw_unit_price, raw_quantity) -> QuotePricingResult:
    """Calculate quote totals using hard-coded tiered discount rules."""
    unit_price = validate_price(raw_unit_price)
    quantity = _validate_quote_quantity(raw_quantity)
    tier = _resolve_discount_tier(quantity)

    subtotal = _to_currency(unit_price * Decimal(quantity))
    discount_amount = _to_currency(subtotal * (tier.discount_percent / PERCENT_BASE))
    final_total = _to_currency(subtotal - discount_amount)

    return QuotePricingResult(
        unit_price=_to_currency(unit_price),
        quantity=quantity,
        tier_name=tier.tier_name,
        discount_description=tier.description,
        discount_percent=tier.discount_percent,
        subtotal=subtotal,
        discount_amount=discount_amount,
        final_total=final_total,
    )


def _validate_quote_quantity(raw_quantity) -> int:
    quantity = validate_quantity(raw_quantity)
    if quantity <= 0:
        raise ValidationError("Quote quantity must be greater than 0")
    return quantity


def _resolve_discount_tier(quantity: int) -> DiscountTier:
    for tier in DISCOUNT_TIERS:
        if quantity > tier.min_quantity_exclusive:
            return tier
    raise ValidationError("Unable to resolve discount tier")


def _to_currency(value: Decimal) -> Decimal:
    return value.quantize(CURRENCY_PRECISION, rounding=ROUND_HALF_UP)
