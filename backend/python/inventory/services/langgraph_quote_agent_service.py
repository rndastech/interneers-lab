from __future__ import annotations

import json
import re
from functools import partial
from typing import Any, Optional, TypedDict

from inventory.domain.exceptions import ValidationError
from inventory.domain.schemas import (
    validate_quote_agent_request,
    validate_quote_agent_response,
)
from inventory.ports.ai_provider import AIProvider
from inventory.ports.logger import ProductLogger
from inventory.services.quote_service import QuoteService
from inventory.services.vector_service import VectorService

try:
    from langgraph.graph import END, StateGraph
except Exception:  # pragma: no cover
    END = "__end__"
    StateGraph = None


# ---------------------------------------------------------------------------
# State — kept intentionally lean.
# The LLM planner reads raw observations and decides what to do next.
# We do NOT pre-classify intent into boolean flags.
# ---------------------------------------------------------------------------

class QuoteAgentState(TypedDict, total=False):
    # ---- raw request ----
    query: str                              # original user text, never mutated
    quantity: int                           # quantity from payload (0 = not provided)
    top_k: int
    category: str
    score_threshold: float
    # ---- planner control ----
    next_action: str
    next_action_args: dict[str, Any]
    action_reason: str
    step_count: int
    max_steps: int
    # ---- running log the LLM planner reads ----
    observations: list[dict[str, Any]]     # append-only log of every tool result
    tools_called: list[str]                # append-only list of tool names used
    # ---- accumulated tool results (raw) ----
    identified_product: dict[str, Any]
    candidate_products: list[dict[str, Any]]
    product_info: dict[str, Any]
    product_info_by_id: dict[str, dict[str, Any]]
    inventory: dict[str, Any]
    quote: dict[str, Any]
    # ---- identification metadata ----
    identification_score: float
    second_best_score: float
    candidate_count: int
    selection_strategy: str
    # ---- final output ----
    response: dict[str, Any]


class AgentStateUpdate(TypedDict, total=False):
    query: str
    quantity: int
    top_k: int
    category: str
    score_threshold: float
    next_action: str
    next_action_args: dict[str, Any]
    action_reason: str
    step_count: int
    max_steps: int
    observations: list[dict[str, Any]]
    tools_called: list[str]
    identified_product: dict[str, Any]
    candidate_products: list[dict[str, Any]]
    product_info: dict[str, Any]
    product_info_by_id: dict[str, dict[str, Any]]
    inventory: dict[str, Any]
    quote: dict[str, Any]
    identification_score: float
    second_best_score: float
    candidate_count: int
    selection_strategy: str
    response: dict[str, Any]


# ---------------------------------------------------------------------------
# Tool catalog — this is the single source of truth the LLM planner reads.
# Adding a new tool = add it here + add its executor below.
# ---------------------------------------------------------------------------

TOOL_CATALOG: dict[str, str] = {
    "search_products": (
        "Search for products by natural language description. "
        "Returns ranked candidates with scores. "
        "Use when you do not yet have a product ID. "
        "Args: {query: str, top_k: int (optional, default 5)}"
    ),
    "get_product_info": (
        "Fetch full product details: name, brand, category, description, specs. "
        "Requires a product ID from a previous search or the user's query. "
        "Args: {product_id: str} or {product_ids: list[str]}"
    ),
    "check_inventory": (
        "Check current stock level for a product. "
        "Returns quantity_available and whether the requested quantity can be fulfilled. "
        "Requires a product ID. "
        "Args: {product_id: str, quantity: int}"
    ),
    "calculate_quote": (
        "Compute pricing: unit price, applicable discounts, and final total. "
        "Requires a product ID and quantity. "
        "Args: {product_id: str, quantity: int}"
    ),
    "build_response": (
        "Assemble and return the final answer to the user from all collected data. "
        "Call this ONLY when you have gathered everything the query needs — no sooner. "
        "Args: {}"
    ),
    "reject": (
        "Decline the request. Use ONLY when: the query is entirely out of domain "
        "(not about products/inventory/pricing), OR a required step has provably failed "
        "and cannot be recovered. "
        "Args: {reason: str}"
    ),
}


# ---------------------------------------------------------------------------
# Standalone tool functions (pure, dependency-injected)
# ---------------------------------------------------------------------------

def _tool_search_products(
    query: str,
    *,
    vector_service: VectorService,
    top_k: Optional[int] = None,
    score_threshold: Optional[float] = None,
    category: Optional[str] = None,
) -> list[dict[str, Any]]:
    return vector_service.top_k_similar_products_with_scores(
        query=query,
        top_k=top_k,
        score_threshold=score_threshold,
        category=category,
    )


def _tool_get_product_info(
    product_id: Optional[str] = None,
    product_ids: Optional[list[str]] = None,
    *,
    quote_service: QuoteService,
) -> dict[str, Any] | dict[str, dict[str, Any]]:
    if product_ids:
        return quote_service.get_products_info(product_ids)
    if product_id:
        return quote_service.get_product_info(product_id)
    raise ValidationError("get_product_info requires product_id or product_ids")


def _tool_check_inventory(product_id: str, *, quote_service: QuoteService) -> dict[str, Any]:
    return quote_service.check_inventory(product_id)


def _tool_calculate_quote(
    product_id: str, quantity: int, *, quote_service: QuoteService
) -> dict[str, Any]:
    return quote_service.calculate_quote(product_id, quantity)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class LangGraphQuoteAgentService:

    DEFAULT_CONFIDENCE_THRESHOLD: float = 0.6
    MIN_SCORE_GAP: float = 0.08
    MAX_AGENT_STEPS: int = 10

    _PRODUCT_ID_PATTERN = re.compile(r"\b([0-9a-f]{24})\b", re.IGNORECASE)

    def __init__(
        self,
        vector_service: VectorService,
        quote_service: QuoteService,
        logger: ProductLogger,
        ai_provider: Optional[AIProvider] = None,
    ) -> None:
        self._vector_service = vector_service
        self._quote_service = quote_service
        self._logger = logger
        self._ai_provider = ai_provider
        self._compiled_graph: Any = None

        # Bind dependencies once
        self._search_products = partial(_tool_search_products, vector_service=self._vector_service)
        self._get_product_info = partial(_tool_get_product_info, quote_service=self._quote_service)
        self._check_inventory = partial(_tool_check_inventory, quote_service=self._quote_service)
        self._calculate_quote = partial(_tool_calculate_quote, quote_service=self._quote_service)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run_quote_agent(self, request_data: dict[str, Any]) -> dict[str, Any]:
        validated = validate_quote_agent_request(request_data)

        # Minimal upfront guard: reject empty/nonsensical queries before spending LLM calls.
        self._basic_query_guard(validated.query)

        explicit_product_id = self._extract_product_id(validated.query)

        initial_state: QuoteAgentState = {
            "query": validated.query,
            "quantity": int(validated.quantity or 0),
            "top_k": validated.top_k,
            "category": validated.category or "",
            "score_threshold": float(validated.score_threshold or 0.0),
            "step_count": 0,
            "max_steps": self.MAX_AGENT_STEPS,
            "observations": [],
            "tools_called": [],
        }

        # If the query contains a hex product ID, seed it so the planner
        # can skip search_products immediately — this is a structural shortcut,
        # not an intent classification.
        if explicit_product_id:
            initial_state["identified_product"] = {"id": explicit_product_id}

        self._logger.info(
            "quote.agent started",
            query=validated.query,
            quantity=initial_state["quantity"],
            explicit_product_id=explicit_product_id,
        )

        graph = self._get_or_build_graph()
        final_state: dict[str, Any] = graph.invoke(initial_state)

        response: dict[str, Any] | None = final_state.get("response")
        if not response:
            raise ValidationError("Quote agent failed to produce a response")

        self._logger.info(
            "quote.agent completed",
            steps=int(final_state.get("step_count", 0)),
            tools_called=final_state.get("tools_called", []),
        )
        return response

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _get_or_build_graph(self) -> Any:
        if self._compiled_graph is not None:
            return self._compiled_graph
        if StateGraph is None:
            raise ValidationError("LangGraph is unavailable.")

        workflow: Any = StateGraph(QuoteAgentState)
        workflow.add_node("plan", self._node_plan)
        workflow.add_node("execute", self._node_execute)

        workflow.set_entry_point("plan")
        workflow.add_conditional_edges(
            "plan",
            lambda s: "execute" if s.get("next_action") not in ("", None) else "__end__",
            {"execute": "execute", "__end__": END},
        )
        workflow.add_conditional_edges(
            "execute",
            self._route_after_execute,
            {"plan": "plan", "end": END},
        )

        self._compiled_graph = workflow.compile()
        return self._compiled_graph

    # ------------------------------------------------------------------
    # Node: plan — LLM decides what to do next, no rule-based gating
    # ------------------------------------------------------------------

    def _node_plan(self, state: QuoteAgentState) -> AgentStateUpdate:
        step_count = int(state.get("step_count") or 0)
        max_steps = int(state.get("max_steps") or self.MAX_AGENT_STEPS)

        if step_count >= max_steps:
            return AgentStateUpdate(
                next_action="reject",
                action_reason=f"Agent exceeded {max_steps} steps without completing the request.",
            )

        decision = self._llm_plan(state)
        return AgentStateUpdate(
            next_action=decision["action"],
            next_action_args=decision.get("args") or {},
            action_reason=decision.get("reason") or "",
        )

    # ------------------------------------------------------------------
    # Node: execute — dispatch to the right tool, record observation
    # ------------------------------------------------------------------

    def _node_execute(self, state: QuoteAgentState) -> AgentStateUpdate:
        action = str(state.get("next_action") or "").strip().lower()
        args: dict[str, Any] = state.get("next_action_args") or {}

        if action == "reject":
            raise ValidationError(
                str(state.get("action_reason") or "Request rejected by agent.")
            )

        # Dispatch
        if action == "search_products":
            update = self._exec_search_products(state, args)
        elif action == "get_product_info":
            update = self._exec_get_product_info(state, args)
        elif action == "check_inventory":
            update = self._exec_check_inventory(state, args)
        elif action == "calculate_quote":
            update = self._exec_calculate_quote(state, args)
        elif action == "build_response":
            update = self._exec_build_response(state)
        else:
            raise ValidationError(f"Unknown action from planner: {action!r}")

        # Append to running logs
        tools_called = list(state.get("tools_called") or [])
        tools_called.append(action)

        observations = list(state.get("observations") or [])
        observation = update.pop("_observation", {})  # type: ignore[misc]
        observation["tool"] = action
        observations.append(observation)

        result = AgentStateUpdate(**update)  # type: ignore[arg-type]
        result["step_count"] = int(state.get("step_count") or 0) + 1
        result["tools_called"] = tools_called
        result["observations"] = observations
        return result

    def _route_after_execute(self, state: QuoteAgentState) -> str:
        if state.get("response"):
            return "end"
        if int(state.get("step_count") or 0) >= int(state.get("max_steps") or self.MAX_AGENT_STEPS):
            return "end"
        return "plan"

    # ------------------------------------------------------------------
    # LLM planner — full authority, reads raw state + observation log
    # ------------------------------------------------------------------

    def _llm_plan(self, state: QuoteAgentState) -> dict[str, Any]:
        """
        The LLM sees: the original query, every tool result so far, and the
        full tool catalog. It decides the single best next action.

        Falls back to a minimal rule-based sequence ONLY if the AI provider
        is unavailable (e.g. in tests).
        """
        if self._ai_provider is not None:
            decision = self._call_planner_llm(state)
            if decision is not None:
                return decision

        return self._fallback_plan(state)

    def _call_planner_llm(self, state: QuoteAgentState) -> Optional[dict[str, Any]]:
        identified: dict[str, Any] = state.get("identified_product") or {}
        observations = state.get("observations") or []
        tools_called = state.get("tools_called") or []

        # Build a concise but complete state snapshot for the LLM
        state_snapshot = {
            "original_query": state.get("query"),
            "quantity_from_payload": state.get("quantity") or "not provided",
            "identified_product_id": identified.get("id") or "none",
            "has_product_info": bool(state.get("product_info")),
            "has_product_info_by_id": bool(state.get("product_info_by_id")),
            "product_info_by_id_count": len(state.get("product_info_by_id") or {}),
            "has_inventory_data": bool(state.get("inventory")),
            "has_quote_data": bool(state.get("quote")),
            "has_candidates": bool(state.get("candidate_products")),
            "tools_called_so_far": tools_called,
            "step_count": state.get("step_count"),
            "observation_log": observations,  # full raw results from every tool call
        }

        tool_descriptions = "\n\n".join(
            f"- **{name}**: {desc}" for name, desc in TOOL_CATALOG.items()
        )

        prompt = f"""You are the decision-making core of an inventory management AI agent.

Your job: decide the SINGLE best next action given the user's query and what has been collected so far.

=== USER QUERY ===
{state.get("query")}

=== CURRENT STATE ===
{json.dumps(state_snapshot, indent=2)}

=== AVAILABLE TOOLS ===
{tool_descriptions}

=== HOW TO DECIDE ===
Read the user's query carefully — not for pre-defined categories, but for what they actually need.
Ask yourself: "What information is still missing to fully answer this query?"

Guidelines:
- If no product_id is known yet → use search_products
- If a product_id is known but product details are missing → use get_product_info  
- If multiple product_ids are known → call get_product_info once with product_ids
- Only fetch inventory data if the user's query requires knowing stock levels or availability
- Only calculate a quote if the user is asking for pricing, a deal, or cost information
- If the user asked for ONLY product details → do NOT call check_inventory or calculate_quote
- If the user asked for ONLY a price → you may skip check_inventory unless availability is relevant
- If the user explicitly names one specific product and says "only this" or equivalent → do NOT return candidates, top_k=1
- Call build_response once ALL required data for the query has been collected — not before
- Never call a tool that already appears in tools_called_so_far
- Use reject ONLY for truly out-of-domain requests (not product/inventory related at all)

=== OUTPUT FORMAT ===
Respond with a single JSON object only. No markdown. No explanation outside the JSON.
Schema: {{"action": "<tool_name>", "reason": "<one sentence>", "args": {{}}}}

Valid action values: {list(TOOL_CATALOG.keys())}
"""

        try:
            response_text, _ = self._ai_provider.generate_response(prompt, temperature=0.0)
        except Exception as exc:
            self._logger.warning("quote.agent planner llm failed", error=str(exc))
            return None

        parsed = self._parse_json(response_text)
        if not isinstance(parsed, dict):
            self._logger.warning("quote.agent planner returned non-JSON", raw=response_text[:300])
            return None

        action = str(parsed.get("action") or "").strip().lower()
        if action not in TOOL_CATALOG:
            self._logger.warning(
                "quote.agent planner chose unknown action",
                action=action,
                allowed=list(TOOL_CATALOG.keys()),
            )
            return None

        return {
            "action": action,
            "reason": str(parsed.get("reason") or ""),
            "args": parsed.get("args") or {},
        }

    def _fallback_plan(self, state: QuoteAgentState) -> dict[str, Any]:
        """
        Minimal sequential fallback when the AI provider is unavailable.
        Executes the most obvious next uncalled tool in dependency order.
        """
        tools_called = set(state.get("tools_called") or [])
        identified: dict[str, Any] = state.get("identified_product") or {}

        if not identified.get("id") and "search_products" not in tools_called:
            return {"action": "search_products", "reason": "fallback: no product id yet", "args": {}}
        if identified.get("id") and not state.get("product_info") and "get_product_info" not in tools_called:
            return {"action": "get_product_info", "reason": "fallback: fetch product details", "args": {}}
        if state.get("product_info") and "build_response" not in tools_called:
            return {"action": "build_response", "reason": "fallback: have product info, build response", "args": {}}
        return {"action": "reject", "reason": "fallback: no valid next action", "args": {"reason": "Could not complete request."}}

    # ------------------------------------------------------------------
    # Tool executors — return AgentStateUpdate with "_observation" key
    # that gets popped by _node_execute before logging.
    # ------------------------------------------------------------------

    def _exec_search_products(
        self, state: QuoteAgentState, args: dict[str, Any]
    ) -> AgentStateUpdate:
        query = str(args.get("query") or state.get("query") or "").strip()
        if not query:
            raise ValidationError("search_products requires a query")

        top_k = int(args.get("top_k") or state.get("top_k") or 5)
        raw_threshold = float(args.get("score_threshold") or state.get("score_threshold") or 0.0) or None
        category = args.get("category") or state.get("category") or None

        products = self._search_products(
            query,
            top_k=top_k,
            score_threshold=raw_threshold,
            category=category or None,
        )
        if not products:
            raise ValidationError("No products matched the request. Try a different description.")

        s0 = float(products[0].get("score", 0.0))
        s1 = float(products[1].get("score", 0.0)) if len(products) > 1 else 0.0
        s2 = float(products[2].get("score", 0.0)) if len(products) > 2 else 0.0
        gap_1_2 = s0 - s1 if len(products) > 1 else s0
        gap_2_3 = s1 - s2 if len(products) > 2 else 0.0

        if s0 < self.DEFAULT_CONFIDENCE_THRESHOLD:
            raise ValidationError(
                f"Best product match score ({s0:.2f}) is below confidence threshold. "
                "Please be more specific."
            )

        selected: dict[str, Any] = products[0].get("product") or {}
        selected_id = str(selected.get("id", ""))
        if not selected_id:
            raise ValidationError("Search returned a product with no ID")

        ambiguous = (
            (len(products) > 1 and gap_1_2 < self.MIN_SCORE_GAP) or
            (len(products) > 2 and gap_2_3 < self.MIN_SCORE_GAP)
        )

        candidates = [
            {
                "product": c.get("product") or {},
                "score": float(c.get("score", 0.0)),
                "vector_id": str(c.get("vector_id", "")),
            }
            for c in products[:5]  # store up to 5 raw candidates
        ]

        strategy = "ambiguous_top_k" if ambiguous else "top_1_clear_winner"

        update = AgentStateUpdate(
            identified_product=selected,
            candidate_products=candidates,
            identification_score=s0,
            second_best_score=s1,
            candidate_count=len(products),
            selection_strategy=strategy,
        )
        # Observation: rich context for the planner's next decision
        update["_observation"] = {  # type: ignore[typeddict-unknown-key]
            "product_count_returned": len(products),
            "top_product_id": selected_id,
            "top_product_name": selected.get("name"),
            "top_score": s0,
            "second_score": s1,
            "score_gap": gap_1_2,
            "ambiguous": ambiguous,
            "all_candidates": [
                {"id": c["product"].get("id"), "name": c["product"].get("name"), "score": c["score"]}
                for c in candidates
            ],
        }
        return update

    def _exec_get_product_info(
        self, state: QuoteAgentState, args: dict[str, Any]
    ) -> AgentStateUpdate:
        raw_product_ids = args.get("product_ids")
        if raw_product_ids is not None:
            if not isinstance(raw_product_ids, list):
                raise ValidationError("get_product_info requires product_ids to be a list")
            product_ids = [str(pid).strip() for pid in raw_product_ids if str(pid).strip()]
            if not product_ids:
                raise ValidationError("get_product_info requires at least one product_id")

            info_by_id = self._get_product_info(product_ids=product_ids)
            update = AgentStateUpdate(product_info_by_id=info_by_id)

            identified_id = str((state.get("identified_product") or {}).get("id") or "")
            if identified_id and identified_id in info_by_id:
                update["product_info"] = info_by_id[identified_id]

            update["_observation"] = {  # type: ignore[typeddict-unknown-key]
                "product_ids": list(info_by_id.keys()),
                "returned_count": len(info_by_id),
            }
            return update

        product_id = str(
            args.get("product_id")
            or (state.get("identified_product") or {}).get("id")
            or ""
        )
        if not product_id:
            raise ValidationError("get_product_info requires a product_id")

        info = self._get_product_info(product_id=product_id)
        update = AgentStateUpdate(product_info=info)
        update["_observation"] = {  # type: ignore[typeddict-unknown-key]
            "product_id": info.get("id"),
            "name": info.get("name"),
            "brand": info.get("brand"),
            "category": info.get("category"),
        }
        return update

    def _exec_check_inventory(
        self, state: QuoteAgentState, args: dict[str, Any]
    ) -> AgentStateUpdate:
        product_id = str(
            args.get("product_id")
            or (state.get("product_info") or {}).get("id")
            or (state.get("identified_product") or {}).get("id")
            or ""
        )
        if not product_id:
            raise ValidationError("check_inventory requires a product_id")

        quantity = int(
            args.get("quantity")
            or state.get("quantity")
            or 1
        )

        inv = dict(self._check_inventory(product_id))
        inv["can_fulfill"] = int(inv.get("quantity_available", 0)) >= quantity
        inv["requested_quantity"] = quantity

        update = AgentStateUpdate(inventory=inv)
        update["_observation"] = {  # type: ignore[typeddict-unknown-key]
            "quantity_available": inv.get("quantity_available"),
            "requested_quantity": quantity,
            "can_fulfill": inv.get("can_fulfill"),
            "in_stock": inv.get("in_stock"),
            "low_stock": inv.get("low_stock"),
        }
        return update

    def _exec_calculate_quote(
        self, state: QuoteAgentState, args: dict[str, Any]
    ) -> AgentStateUpdate:
        product_id = str(
            args.get("product_id")
            or (state.get("product_info") or {}).get("id")
            or (state.get("identified_product") or {}).get("id")
            or ""
        )
        if not product_id:
            raise ValidationError("calculate_quote requires a product_id")

        quantity = int(
            args.get("quantity")
            or state.get("quantity")
            or 1
        )
        if quantity <= 0:
            raise ValidationError("Quantity must be greater than 0")

        qt = self._calculate_quote(product_id, quantity)
        update = AgentStateUpdate(quote=qt)
        update["_observation"] = {  # type: ignore[typeddict-unknown-key]
            "product_id": qt.get("product_id"),
            "quantity": qt.get("quantity"),
            "unit_price": qt.get("unit_price"),
            "discount_percent": qt.get("discount_percent"),
            "discount_description": qt.get("discount_description"),
            "final_total": qt.get("final_total"),
        }
        return update

    def _exec_build_response(self, state: QuoteAgentState) -> AgentStateUpdate:
        """
        Assembles ONLY the data that was actually fetched.
        No flags needed — if inventory is in state, include it; if not, omit it.
        The LLM planner already decided what to fetch based on the query.
        """
        product: dict[str, Any] = state.get("product_info") or {}
        if not product:
            raise ValidationError("Cannot build response: product info was never fetched")

        inventory: Optional[dict[str, Any]] = state.get("inventory") or None
        quote: Optional[dict[str, Any]] = state.get("quote") or None
        candidates_raw: list[dict[str, Any]] = state.get("candidate_products") or []

        quantity = int(
            state.get("quantity")
            or (quote.get("quantity") if quote else 0)
            or 0
        )

        # Detect whether the name the user typed matches what was found.
        # Used in metadata and passed to summary builder for honest communication.
        query_text = str(state.get("query") or "")
        found_name = str(product.get("name", ""))
        name_matched_exactly = found_name.lower() in query_text.lower()

        # Only include candidates if multiple were fetched AND quote data exists for them
        # (i.e. the planner decided this was a multi-product comparison query)
        candidates_payload: list[dict[str, Any]] = []
        selected_id = str(product.get("id", ""))
        info_by_id: dict[str, dict[str, Any]] = dict(state.get("product_info_by_id") or {})
        if len(candidates_raw) > 1 and quote:
            ids_to_fetch: list[str] = []
            for c in candidates_raw[:3]:
                cp = c.get("product") or {}
                cid = str(cp.get("id", ""))
                if not cid or cid == selected_id:
                    continue
                if cid not in info_by_id:
                    ids_to_fetch.append(cid)

            if ids_to_fetch:
                ids_to_fetch = list(dict.fromkeys(ids_to_fetch))
                fetched_info = self._get_product_info(product_ids=ids_to_fetch)
                info_by_id.update(fetched_info)

            for rank, c in enumerate(candidates_raw[:3], start=1):
                cp = c.get("product") or {}
                cid = str(cp.get("id", ""))
                if not cid:
                    continue
                if cid == selected_id:
                    c_info, c_inv, c_quote = product, inventory, quote
                else:
                    c_info = info_by_id.get(cid)
                    if not c_info:
                        continue
                    raw_inv = dict(self._check_inventory(cid))
                    raw_inv["can_fulfill"] = int(raw_inv.get("quantity_available", 0)) >= quantity
                    c_inv = raw_inv
                    c_quote = self._calculate_quote(cid, quantity) if quantity else None
                candidates_payload.append({
                    "identified_product": self._product_payload(c_info),
                    "inventory": self._inventory_payload(c_inv) if c_inv else None,
                    "discount": self._discount_payload(c_quote) if c_quote else None,
                    "quote": self._quote_payload(c_quote) if c_quote else None,
                    "metadata": {"rank": rank, "score": float(c.get("score", 0.0))},
                })

        payload: dict[str, Any] = {
            "request": query_text,
            "identified_product": self._product_payload(product),
            "inventory": self._inventory_payload(inventory) if inventory else None,
            "discount": self._discount_payload(quote) if quote else None,
            "quote": self._quote_payload(quote) if quote else None,
            "summary": self._build_summary(
                query=query_text,
                product=product,
                inventory=inventory,
                quote=quote,
                quantity=quantity,
                observations=state.get("observations") or [],
                name_matched_exactly=name_matched_exactly,
                identification_score=float(state.get("identification_score") or 0.0),
            ),
            "metadata": {
                "component": "LangGraphQuoteAgentService",
                "agent_mode": "llm_driven_dynamic",
                "agent_steps": int(state.get("step_count") or 0),
                "candidate_count": int(state.get("candidate_count") or 0),
                "selection_strategy": str(state.get("selection_strategy") or ""),
                "identification_score": state.get("identification_score"),
                "second_best_score": state.get("second_best_score"),
                "name_matched_exactly": name_matched_exactly,
                "tools_called": state.get("tools_called") or [],
            },
        }
        if candidates_payload:
            payload["candidates"] = candidates_payload

        validated = validate_quote_agent_response(payload)
        update = AgentStateUpdate(response=validated.model_dump())
        update["_observation"] = {"response_built": True}  # type: ignore[typeddict-unknown-key]
        return update

    # ------------------------------------------------------------------
    # Summary — LLM-generated so it can honestly describe what happened:
    # typo corrections, fuzzy matches, exact-match confirmations, etc.
    # Falls back to structured plain-text if the AI provider is unavailable.
    # ------------------------------------------------------------------

    def _build_summary(
        self,
        *,
        query: str,
        product: dict[str, Any],
        inventory: Optional[dict[str, Any]],
        quote: Optional[dict[str, Any]],
        quantity: int,
        observations: list[dict[str, Any]],
        name_matched_exactly: bool,
        identification_score: float,
    ) -> str:
        if self._ai_provider is not None:
            llm_summary = self._llm_build_summary(
                query=query,
                product=product,
                inventory=inventory,
                quote=quote,
                quantity=quantity,
                observations=observations,
                name_matched_exactly=name_matched_exactly,
                identification_score=identification_score,
            )
            if llm_summary:
                return llm_summary

        # Fallback: structured plain-text, always honest about name mismatches
        return self._fallback_summary(
            query=query,
            product=product,
            inventory=inventory,
            quote=quote,
            quantity=quantity,
            name_matched_exactly=name_matched_exactly,
            identification_score=identification_score,
        )

    def _llm_build_summary(
        self,
        *,
        query: str,
        product: dict[str, Any],
        inventory: Optional[dict[str, Any]],
        quote: Optional[dict[str, Any]],
        quantity: int,
        observations: list[dict[str, Any]],
        name_matched_exactly: bool,
        identification_score: float,
    ) -> Optional[str]:
        """
        Ask the LLM to write a plain-English summary of what happened.
        It has full context: original query, what was found, match quality,
        and the complete observation log — so it can describe any situation
        honestly without pre-baked templates.
        """
        data_collected: dict[str, Any] = {
            "product": {
                "id": product.get("id"),
                "name": product.get("name"),
                "brand": product.get("brand"),
                "category": product.get("category"),
            },
            "inventory": {
                "quantity_available": inventory.get("quantity_available"),
                "can_fulfill": inventory.get("can_fulfill"),
                "in_stock": inventory.get("in_stock"),
            } if inventory else None,
            "quote": {
                "unit_price": quote.get("unit_price"),
                "discount_percent": quote.get("discount_percent"),
                "tier_name": quote.get("tier_name"),
                "final_total": quote.get("final_total"),
                "quantity": quote.get("quantity"),
            } if quote else None,
        }

        prompt = f"""You are writing the "summary" field of an inventory agent API response.

=== ORIGINAL USER QUERY ===
{query}

=== WHAT THE AGENT FOUND ===
{json.dumps(data_collected, indent=2)}

=== MATCH QUALITY ===
- Identification score: {identification_score:.4f} (1.0 = perfect, 0.6 = minimum threshold)
- Name matched query exactly: {name_matched_exactly}
- Quantity requested: {quantity or "not specified"}

=== AGENT OBSERVATION LOG ===
{json.dumps(observations, indent=2)}

=== INSTRUCTIONS ===
Write a concise plain-English summary (3-6 sentences) that:
1. States clearly which product was found and its key details.
2. If the user typed a name that doesn't exactly match the found product name, 
   explicitly acknowledge the discrepancy — e.g. "Note: your query contained a typo 
   ('Gandme'); the closest matching product is 'TitanCore G7 Gaming Motherboard'."
3. If identification_score < 0.95, note that this is a fuzzy/closest match, 
   not a guaranteed exact match.
4. Include inventory status only if inventory data was fetched.
5. Include pricing only if quote data was fetched.
6. If neither inventory nor quote was fetched, confirm the product details were retrieved 
   as requested and nothing else.

Do NOT use bullet points. Write flowing sentences only.
Do NOT include JSON, field names, or technical jargon.
Respond with the summary text only — nothing else.
"""

        try:
            summary_text, _ = self._ai_provider.generate_response(prompt, temperature=0.1)
            cleaned = summary_text.strip()
            if len(cleaned) > 20:  # sanity check: reject empty/junk responses
                return cleaned
        except Exception as exc:
            self._logger.warning("quote.agent summary llm failed", error=str(exc))

        return None

    def _fallback_summary(
        self,
        *,
        query: str,
        product: dict[str, Any],
        inventory: Optional[dict[str, Any]],
        quote: Optional[dict[str, Any]],
        quantity: int,
        name_matched_exactly: bool,
        identification_score: float,
    ) -> str:
        """
        Structured plain-text fallback. Always surfaces name mismatches
        and match confidence so the caller is never silently misled.
        """
        name = str(product.get("name", "")) or "Unknown product"
        brand = str(product.get("brand", ""))
        label = f"{name} ({brand})" if brand else name
        lines: list[str] = [f"Product: {label}"]

        # Surface name mismatch — critical for user trust
        if not name_matched_exactly:
            lines.append(
                f"Note: the product name in your query did not exactly match. "
                f"Closest match found: \"{name}\" "
                f"(confidence score: {identification_score:.2f})."
            )
        elif identification_score < 0.95:
            lines.append(
                f"Match confidence: {identification_score:.2f} "
                f"(fuzzy match — not guaranteed exact)."
            )

        category = str(product.get("category", ""))
        if category:
            lines.append(f"Category: {category}")
        if quantity:
            lines.append(f"Requested quantity: {quantity}")

        if inventory:
            qty_avail = int(inventory.get("quantity_available", 0))
            can = bool(inventory.get("can_fulfill", False))
            lines.append(
                f"Stock: {qty_avail} available "
                f"({'can fulfill' if can else 'cannot fulfill'} request)."
            )

        if quote:
            unit_price = float(quote.get("unit_price", 0.0))
            discount_pct = float(quote.get("discount_percent", 0.0))
            tier_name = str(quote.get("tier_name", "standard"))
            final_total = float(quote.get("final_total", 0.0))
            lines.append(f"Unit price: ${unit_price:.2f}.")
            if discount_pct > 0:
                lines.append(f"Discount: {discount_pct:.0f}% ({tier_name}).")
            lines.append(f"Final total: ${final_total:.2f}.")
        elif inventory is None:
            lines.append("Inventory and pricing were not requested.")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Payload builders
    # ------------------------------------------------------------------

    @staticmethod
    def _product_payload(p: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(p.get("id", "")),
            "name": str(p.get("name", "")),
            "category": str(p.get("category", "")),
            "brand": str(p.get("brand", "")),
        }

    @staticmethod
    def _inventory_payload(inv: dict[str, Any]) -> dict[str, Any]:
        return {
            "quantity_available": int(inv.get("quantity_available", 0)),
            "minimum_stock_level": int(inv.get("minimum_stock_level", 0)),
            "in_stock": bool(inv.get("in_stock", False)),
            "low_stock": bool(inv.get("low_stock", False)),
            "can_fulfill": bool(inv.get("can_fulfill", False)),
        }

    @staticmethod
    def _discount_payload(qt: dict[str, Any]) -> dict[str, Any]:
        return {
            "tier_name": str(qt.get("tier_name", "standard")),
            "discount_percent": float(qt.get("discount_percent", 0.0)),
            "discount_amount": float(qt.get("discount_amount", 0.0)),
        }

    @staticmethod
    def _quote_payload(qt: dict[str, Any]) -> dict[str, Any]:
        return {
            "product_id": str(qt.get("product_id", "")),
            "product_name": str(qt.get("product_name", "")),
            "unit_price": float(qt.get("unit_price", 0.0)),
            "quantity": int(qt.get("quantity", 0)),
            "subtotal": float(qt.get("subtotal", 0.0)),
            "final_total": float(qt.get("final_total", 0.0)),
        }

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _extract_product_id(self, query: str) -> Optional[str]:
        m = self._PRODUCT_ID_PATTERN.search(query)
        return m.group(1).lower() if m else None

    @staticmethod
    def _basic_query_guard(query: str) -> None:
        """
        Absolute minimum upfront validation — only catches structurally
        broken inputs. Intent classification is left to the LLM planner.
        """
        q = query.strip()
        if not q:
            raise ValidationError("Query must not be empty")
        if len(q) < 3:
            raise ValidationError("Query is too short")
        if not re.search(r"[a-zA-Z]", q):
            raise ValidationError("Query must contain text")

    @staticmethod
    def _parse_json(text: str) -> Optional[dict[str, Any]]:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:].strip().removesuffix("```").strip()
        elif text.startswith("```"):
            text = text[3:].strip().removesuffix("```").strip()
        try:
            result = json.loads(text)
            return result if isinstance(result, dict) else None
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try:
                    result = json.loads(m.group(0))
                    return result if isinstance(result, dict) else None
                except json.JSONDecodeError:
                    pass
        return None