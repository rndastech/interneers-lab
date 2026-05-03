from __future__ import annotations

from decimal import Decimal
from typing import Any

from inventory.domain.quote_pricing import calculate_quote_pricing
from inventory.ports.logger import ProductLogger
from inventory.services.product_service import ProductService


class QuoteService:

    def __init__(self, product_service: ProductService, logger: ProductLogger) -> None:
        self._product_service = product_service
        self._logger = logger

    def _build_product_info(self, product: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(product.get("id", "")),
            "name": str(product.get("name", "")),
            "category": str(product.get("category", "")),
            "brand": str(product.get("brand", "")),
            "price": self._to_float(product.get("price", Decimal("0"))),
            "quantity": int(product.get("quantity", 0)),
            "minimum_stock_level": int(product.get("minimum_stock_level", 0)),
        }

    def get_product_info(self, product_id: str) -> dict[str, Any]:
        product = self._product_service.get_product(product_id)
        result = self._build_product_info(product)
        self._logger.debug(
            "quote.get_product_info completed",
            product_id=result["id"],
            product_name=result["name"],
        )
        return result

    def get_products_info(self, product_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not product_ids:
            return {}

        unique_ids = list(dict.fromkeys(product_ids))
        products_by_id = self._product_service.get_many_by_ids(unique_ids)
        results: dict[str, dict[str, Any]] = {}

        for product_id in unique_ids:
            product = products_by_id.get(product_id)
            if not product:
                continue
            results[product_id] = self._build_product_info(product)

        self._logger.debug(
            "quote.get_products_info completed",
            requested_count=len(unique_ids),
            returned_count=len(results),
        )
        return results

    def check_inventory(self, product_id: str) -> dict[str, Any]:
        product = self._product_service.get_product(product_id)
        quantity_available = int(product.get("quantity", 0))
        minimum_stock_level = int(product.get("minimum_stock_level", 0))
        inventory = {
            "quantity_available": quantity_available,
            "minimum_stock_level": minimum_stock_level,
            "in_stock": quantity_available > 0,
            "low_stock": quantity_available <= minimum_stock_level,
        }
        self._logger.debug(
            "quote.check_inventory completed",
            product_id=str(product.get("id", "")),
            quantity_available=quantity_available,
            minimum_stock_level=minimum_stock_level,
        )
        return inventory

    def calculate_quote(self, product_id: str, quantity: int) -> dict[str, Any]:
        product = self._product_service.get_product(product_id)
        pricing = calculate_quote_pricing(product.get("price"), quantity)
        quote = {
            "product_id": str(product.get("id", "")),
            "product_name": str(product.get("name", "")),
            "unit_price": self._to_float(pricing.unit_price),
            "quantity": pricing.quantity,
            "tier_name": pricing.tier_name,
            "discount_description": pricing.discount_description,
            "discount_percent": self._to_float(pricing.discount_percent),
            "subtotal": self._to_float(pricing.subtotal),
            "discount_amount": self._to_float(pricing.discount_amount),
            "final_total": self._to_float(pricing.final_total),
        }
        self._logger.debug(
            "quote.calculate_quote completed",
            product_id=quote["product_id"],
            quantity=quote["quantity"],
            tier_name=quote["tier_name"],
            final_total=quote["final_total"],
        )
        return quote

    @staticmethod
    def _to_float(value: Any) -> float:
        return float(value)
