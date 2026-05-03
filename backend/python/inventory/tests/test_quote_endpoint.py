from unittest import TestCase
from unittest.mock import Mock, patch
from typing import Any, cast

from rest_framework.test import APIRequestFactory

from inventory import views
from inventory.domain.exceptions import ValidationError


class TestQuoteEndpoint(TestCase):

    def setUp(self):
        self.factory = APIRequestFactory()

    @patch("inventory.views.quote_agent_service")
    def test_quote_endpoint_success(self, mock_quote_agent_service: Mock):
        mock_quote_agent_service.run_quote_agent.return_value = {
            "request": "I need 60 building blocks",
            "identified_product": {
                "id": "65f1a2b3c4d5e6f7a8b9c0d1",
                "name": "Lego Classic Building Blocks",
                "category": "toys",
                "brand": "lego",
            },
            "inventory": {
                "quantity_available": 125,
                "minimum_stock_level": 20,
                "in_stock": True,
                "low_stock": False,
                "can_fulfill": True,
            },
            "discount": {
                "tier_name": "bulk_50_plus",
                "discount_percent": 10.0,
                "discount_amount": 120.0,
            },
            "quote": {
                "product_id": "65f1a2b3c4d5e6f7a8b9c0d1",
                "product_name": "Lego Classic Building Blocks",
                "unit_price": 20.0,
                "quantity": 60,
                "subtotal": 1200.0,
                "final_total": 1080.0,
            },
            "metadata": {"component": "LangGraphQuoteAgentService"},
        }

        request = self.factory.post(
            "/inventory/ai/quote/",
            {"query": "I need 60 building blocks"},
            format="json",
        )
        response = views.ai_quote(request)
        response_data = cast(Any, response).data

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response_data["quote"]["quantity"], 60)

    def test_quote_endpoint_invalid_payload(self):
        request = self.factory.post("/inventory/ai/quote/", {}, format="json")
        response = views.ai_quote(request)
        response_data = cast(Any, response).data

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response_data)

    @patch("inventory.views.quote_agent_service")
    def test_quote_endpoint_unknown_product(self, mock_quote_agent_service: Mock):
        mock_quote_agent_service.run_quote_agent.side_effect = ValidationError("No product matched the request")

        request = self.factory.post(
            "/inventory/ai/quote/",
            {"query": "I need 60 unknown blocks"},
            format="json",
        )
        response = views.ai_quote(request)
        response_data = cast(Any, response).data

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response_data["error"], "No product matched the request")

    @patch("inventory.views.quote_agent_service")
    def test_quote_endpoint_insufficient_inventory(self, mock_quote_agent_service: Mock):
        mock_quote_agent_service.run_quote_agent.side_effect = ValidationError("Inventory cannot fulfill requested quantity")

        request = self.factory.post(
            "/inventory/ai/quote/",
            {"query": "I need 600 building blocks"},
            format="json",
        )
        response = views.ai_quote(request)
        response_data = cast(Any, response).data

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response_data["error"], "Inventory cannot fulfill requested quantity")
