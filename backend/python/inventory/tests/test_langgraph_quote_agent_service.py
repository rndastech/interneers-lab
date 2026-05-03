from typing import Any, cast
from unittest import TestCase
from unittest.mock import patch

from inventory.domain.exceptions import ValidationError
from inventory.services.langgraph_quote_agent_service import (
    LangGraphQuoteAgentService,
    calculate_quote,
    check_inventory,
    get_product_info,
)


class _NoopLogger:
    def debug(self, *_args, **_kwargs):
        return None

    def info(self, *_args, **_kwargs):
        return None


class _FakeVectorService:
    def __init__(self, products: list[dict]):
        self._products = products
        self.last_query = None
        self.call_count = 0

    def top_k_similar_products_with_scores(self, **kwargs):
        self.call_count += 1
        self.last_query = kwargs.get("query")
        return [
            {
                "product": dict(product),
                "score": float(product.get("_score", 0.9)),
                "vector_id": str(product.get("id", "")),
            }
            for product in self._products
        ]


class _FakeQuoteService:
    def __init__(self):
        self.calls = []

    def get_product_info(self, product_id: str):
        self.calls.append(("get_product_info", product_id))
        return {
            "id": product_id,
            "name": "Lego Classic Building Blocks",
            "category": "toys",
            "brand": "lego",
            "price": 20.0,
            "quantity": 125,
            "minimum_stock_level": 20,
        }

    def check_inventory(self, product_id: str):
        self.calls.append(("check_inventory", product_id))
        return {
            "quantity_available": 125,
            "minimum_stock_level": 20,
            "in_stock": True,
            "low_stock": False,
        }

    def calculate_quote(self, product_id: str, quantity: int):
        self.calls.append(("calculate_quote", product_id, quantity))
        return {
            "product_id": product_id,
            "product_name": "Lego Classic Building Blocks",
            "unit_price": 20.0,
            "quantity": quantity,
            "tier_name": "bulk_50_plus",
            "discount_description": "10% off for quantities over 50",
            "discount_percent": 10.0,
            "subtotal": 1200.0,
            "discount_amount": 120.0,
            "final_total": 1080.0,
        }


class _FakeAIProvider:
    def __init__(self, response_text: str):
        self._response_text = response_text

    def generate_response(self, _prompt: str, **_kwargs):
        return self._response_text, {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}


class _SequenceAIProvider:
    def __init__(self, responses: list[str]):
        self._responses = list(responses)

    def generate_response(self, _prompt: str, **_kwargs):
        if self._responses:
            response = self._responses.pop(0)
        else:
            response = '{"action": "build_invoice", "reason": "complete"}'
        return response, {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}


class _SequentialGraph:
    def __init__(self, service: LangGraphQuoteAgentService):
        self._service = service

    def invoke(self, state):
        next_state = dict(state)
        next_state.update(self._service._node_top_k_products(cast(Any, next_state), {}))
        next_state.update(self._service._node_get_product_info(cast(Any, next_state)))
        next_state.update(self._service._node_check_inventory(cast(Any, next_state)))
        if next_state.get("needs_quote"):
            next_state.update(self._service._node_calculate_quote(cast(Any, next_state)))
        next_state.update(self._service._node_build_invoice(cast(Any, next_state)))
        return next_state


class TestLangGraphQuoteAgentService(TestCase):

    def setUp(self):
        self.vector_service = _FakeVectorService(
            products=[
                {
                    "id": "65f1a2b3c4d5e6f7a8b9c0d1",
                    "name": "Lego Classic Building Blocks",
                    "category": "toys",
                    "brand": "lego",
                }
            ]
        )
        self.quote_service = _FakeQuoteService()
        self.service = LangGraphQuoteAgentService(
            vector_service=cast(Any, self.vector_service),
            quote_service=cast(Any, self.quote_service),
            logger=cast(Any, _NoopLogger()),
        )

    def test_explicit_tool_functions_delegate_to_quote_service(self):
        product_info = get_product_info("product-1", quote_service=cast(Any, self.quote_service))
        inventory = check_inventory("product-1", quote_service=cast(Any, self.quote_service))
        quote = calculate_quote("product-1", 60, quote_service=cast(Any, self.quote_service))

        self.assertEqual(product_info["id"], "product-1")
        self.assertEqual(inventory["quantity_available"], 125)
        self.assertEqual(quote["quantity"], 60)

    def test_run_quote_agent_returns_invoice_payload(self):
        with patch.object(self.service, "_get_or_build_graph", return_value=_SequentialGraph(self.service)):
            response = self.service.run_quote_agent(
                {
                    "query": "I need 60 building blocks for a school project, can I get a deal?",
                    "top_k": 5,
                }
            )

        self.assertEqual(response["identified_product"]["name"], "Lego Classic Building Blocks")
        self.assertEqual(response["quote"]["quantity"], 60)
        self.assertTrue(response["inventory"]["can_fulfill"])
        self.assertIn("building blocks", self.vector_service.last_query)
        self.assertIn("school", self.vector_service.last_query)
        self.assertEqual(
            [call[0] for call in self.quote_service.calls[-3:]],
            ["get_product_info", "check_inventory", "calculate_quote"],
        )

    def test_run_quote_agent_rejects_low_confidence_match(self):
        service = LangGraphQuoteAgentService(
            vector_service=cast(
                Any,
                _FakeVectorService(
                    products=[
                        {
                            "id": "65f1a2b3c4d5e6f7a8b9c0d1",
                            "name": "Lego Classic Building Blocks",
                            "category": "toys",
                            "brand": "lego",
                            "_score": 0.1,
                        }
                    ]
                ),
            ),
            quote_service=cast(Any, _FakeQuoteService()),
            logger=cast(Any, _NoopLogger()),
        )

        with patch.object(service, "_get_or_build_graph", return_value=_SequentialGraph(service)):
            with self.assertRaises(ValidationError):
                service.run_quote_agent(
                    {
                        "query": "I need 60 building blocks",
                        "top_k": 5,
                    }
                )

    def test_run_quote_agent_rejects_irrelevant_query(self):
        with patch.object(self.service, "_get_or_build_graph", return_value=_SequentialGraph(self.service)):
            with self.assertRaises(ValidationError):
                self.service.run_quote_agent(
                    {
                        "query": "please can i get a deal thanks",
                        "quantity": 10,
                        "top_k": 5,
                    }
                )

    def test_run_quote_agent_rejects_non_inventory_query_before_vector_search(self):
        with patch.object(self.service, "_get_or_build_graph", return_value=_SequentialGraph(self.service)):
            with self.assertRaises(ValidationError):
                self.service.run_quote_agent(
                    {
                        "query": "who was orange cap winner ipl 2024",
                        "top_k": 5,
                    }
                )

        self.assertEqual(self.vector_service.call_count, 0)

    def test_run_quote_agent_defaults_quantity_to_one_when_not_detected(self):
        with patch.object(self.service, "_get_or_build_graph", return_value=_SequentialGraph(self.service)):
            response = self.service.run_quote_agent(
                {
                    "query": "Need lego building blocks for classroom activity",
                    "top_k": 5,
                }
            )

        self.assertIsNone(response["quote"])
        self.assertEqual(response["metadata"]["quantity_source"], "default")

    def test_run_quote_agent_does_not_treat_standalone_year_as_quantity(self):
        with patch.object(self.service, "_get_or_build_graph", return_value=_SequentialGraph(self.service)):
            response = self.service.run_quote_agent(
                {
                    "query": "Need lego building blocks version 2024 for physics experiment",
                    "top_k": 5,
                }
            )

        self.assertIsNone(response["quote"])
        self.assertEqual(response["metadata"]["quantity_source"], "default")

    def test_run_quote_agent_returns_candidates_when_ambiguous(self):
        service = LangGraphQuoteAgentService(
            vector_service=cast(
                Any,
                _FakeVectorService(
                    products=[
                        {
                            "id": "65f1a2b3c4d5e6f7a8b9c0d1",
                            "name": "Lego Classic Building Blocks",
                            "category": "toys",
                            "brand": "lego",
                            "_score": 0.86,
                        },
                        {
                            "id": "75f1a2b3c4d5e6f7a8b9c0d2",
                            "name": "Mega Building Blocks",
                            "category": "toys",
                            "brand": "mega",
                            "_score": 0.83,
                        },
                    ]
                ),
            ),
            quote_service=cast(Any, _FakeQuoteService()),
            logger=cast(Any, _NoopLogger()),
        )

        with patch.object(service, "_get_or_build_graph", return_value=_SequentialGraph(service)):
            response = service.run_quote_agent(
                {
                    "query": "I need 60 building blocks for classroom activity",
                    "top_k": 5,
                }
            )

        self.assertEqual(response["metadata"]["selection_strategy"], "vector_top_3_ambiguous")
        self.assertEqual(len(response["candidates"]), 2)
        self.assertIsNone(response["quote"])
        self.assertEqual(
            [candidate["identified_product"]["id"] for candidate in response["candidates"]],
            [
                "65f1a2b3c4d5e6f7a8b9c0d1",
                "75f1a2b3c4d5e6f7a8b9c0d2",
            ],
        )

    def test_run_quote_agent_returns_candidates_for_quote_requests_with_multiple_products(self):
        service = LangGraphQuoteAgentService(
            vector_service=cast(
                Any,
                _FakeVectorService(
                    products=[
                        {
                            "id": "65f1a2b3c4d5e6f7a8b9c0d1",
                            "name": "Lego Classic Building Blocks",
                            "category": "toys",
                            "brand": "lego",
                            "_score": 0.95,
                        },
                        {
                            "id": "75f1a2b3c4d5e6f7a8b9c0d2",
                            "name": "Mega Building Blocks",
                            "category": "toys",
                            "brand": "mega",
                            "_score": 0.5,
                        },
                    ]
                ),
            ),
            quote_service=cast(Any, _FakeQuoteService()),
            logger=cast(Any, _NoopLogger()),
        )

        with patch.object(service, "_get_or_build_graph", return_value=_SequentialGraph(service)):
            response = service.run_quote_agent(
                {
                    "query": "I need 5 building blocks for class, can I get a deal?",
                    "top_k": 5,
                }
            )

        self.assertEqual(response["metadata"]["selection_strategy"], "vector_top_3_for_quote")
        self.assertEqual(len(response["candidates"]), 2)
        self.assertIsNotNone(response["quote"])
        self.assertTrue(all(candidate["quote"] is not None for candidate in response["candidates"]))

    def test_run_quote_agent_uses_llm_analysis_when_available(self):
        service = LangGraphQuoteAgentService(
            vector_service=cast(Any, _FakeVectorService(products=self.vector_service._products)),
            quote_service=cast(Any, _FakeQuoteService()),
            logger=cast(Any, _NoopLogger()),
            ai_provider=cast(
                Any,
                _FakeAIProvider(
                    '{"is_inventory_intent": true, "is_inventory_domain": true, "lookup_query": "lego classic building blocks for physics experiment", "quantity": 12, "reason": ""}'
                ),
            ),
        )

        with patch.object(service, "_get_or_build_graph", return_value=_SequentialGraph(service)):
            response = service.run_quote_agent(
                {
                    "query": "I need lego blocks for the experiment",
                    "top_k": 5,
                }
            )

        self.assertIsNone(response["quote"])
        self.assertIn("Requested quantity: 12", response["summary"])
        self.assertEqual(response["metadata"]["analysis_source"], "llm")

    def test_planner_uses_llm_next_action_when_valid(self):
        service = LangGraphQuoteAgentService(
            vector_service=cast(Any, _FakeVectorService(products=self.vector_service._products)),
            quote_service=cast(Any, _FakeQuoteService()),
            logger=cast(Any, _NoopLogger()),
            ai_provider=cast(
                Any,
                _SequenceAIProvider(
                    responses=[
                        '{"action": "top_k_products", "reason": "start with search"}',
                    ]
                ),
            ),
        )

        state = {
            "query": "I need 5 lego building blocks",
            "lookup_query": "lego building blocks",
            "quantity": 5,
            "step_count": 0,
            "max_steps": 8,
        }
        update = service._node_plan_next_action(cast(Any, state))

        self.assertEqual(update["next_action"], "top_k_products")
        self.assertEqual(update["action_reason"], "start with search")

    def test_planner_falls_back_when_llm_returns_invalid_action(self):
        service = LangGraphQuoteAgentService(
            vector_service=cast(Any, _FakeVectorService(products=self.vector_service._products)),
            quote_service=cast(Any, _FakeQuoteService()),
            logger=cast(Any, _NoopLogger()),
            ai_provider=cast(
                Any,
                _SequenceAIProvider(
                    responses=[
                        '{"action": "do_something_else", "reason": "invalid"}',
                    ]
                ),
            ),
        )

        state = {
            "query": "I need 5 lego building blocks",
            "lookup_query": "lego building blocks",
            "quantity": 5,
            "step_count": 0,
            "max_steps": 8,
        }
        update = service._node_plan_next_action(cast(Any, state))

        self.assertEqual(update["next_action"], "top_k_products")
        self.assertEqual(update["action_reason"], "rule_based_fallback")

    def test_run_quote_agent_rejects_with_llm_intent_gate(self):
        service = LangGraphQuoteAgentService(
            vector_service=cast(Any, _FakeVectorService(products=self.vector_service._products)),
            quote_service=cast(Any, _FakeQuoteService()),
            logger=cast(Any, _NoopLogger()),
            ai_provider=cast(
                Any,
                _FakeAIProvider(
                    '{"is_inventory_intent": false, "is_inventory_domain": false, "lookup_query": "orange cap winner ipl", "quantity": null, "reason": "sports query"}'
                ),
            ),
        )

        with patch.object(service, "_get_or_build_graph", return_value=_SequentialGraph(service)):
            with self.assertRaises(ValidationError):
                service.run_quote_agent(
                    {
                        "query": "I need 10 building blocks",
                        "top_k": 5,
                    }
                )

    def test_run_quote_agent_rejects_weak_semantic_query(self):
        with patch.object(self.service, "_get_or_build_graph", return_value=_SequentialGraph(self.service)):
            with self.assertRaises(ValidationError):
                self.service.run_quote_agent(
                    {
                        "query": "blocks",
                        "top_k": 5,
                    }
                )

    def test_run_quote_agent_raises_when_no_product_matches(self):
        service = LangGraphQuoteAgentService(
            vector_service=cast(Any, _FakeVectorService(products=[])),
            quote_service=cast(Any, _FakeQuoteService()),
            logger=cast(Any, _NoopLogger()),
        )

        with patch.object(service, "_get_or_build_graph", return_value=_SequentialGraph(service)):
            with self.assertRaises(ValidationError):
                service.run_quote_agent({"query": "unknown product", "top_k": 5})
