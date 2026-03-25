from typing import Dict, Any, List, Optional
from pydantic import ValidationError as PydanticValidationError
from inventory.domain.schemas import (
    TextGenerationRequestSchema,
    ProductGenerationRequestSchema,
    GeneratedProductSchema,
    GeneratedProductListSchema,
    validate_text_gen,
    validate_product_gen,
    extract_config,
    validate_products_schema,
)
from inventory.domain.exceptions import ValidationError
from inventory.domain.sys_prompts import (
    GENERATE_PRODUCTS_PROMPT,
    CATEGORY_CONSTRAINT_PROMPT_TEMPLATE,
    CATEGORY_OPTIONAL_PROMPT,
    SPECIAL_INSTRUCTIONS_DEFAULT,
    SCENARIO_HOLIDAY_RUSH,
    SCENARIO_FLASH_SALE,
    SCENARIO_BACK_TO_SCHOOL,
    SCENARIO_PREMIUM_ELECTRONICS,
    SCENARIO_WAREHOUSE_OVERSTOCK,
)
from inventory.domain.parser import AIResponseParser
from inventory.ports.ai_provider import AIProvider
from inventory.ports.logger import ProductLogger
from inventory.ports.product_repository import ProductRepository


class AIService:

    def __init__(self, ai_provider: AIProvider, logger: ProductLogger, product_repository: ProductRepository, category_service, product_service):
        self._provider = ai_provider
        self._logger = logger
        self._product_repository = product_repository
        self._category_service = category_service
        self._product_service = product_service

    def generate_text(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        operation_name = "generate_text"
        self._logger.debug(f"{operation_name} initiated")
        try:
            validated_request = validate_text_gen(request_data)
            generation_config = extract_config(validated_request)
            response_text = self._provider.generate_response(
                validated_request.prompt, **generation_config
            )
            self._logger.info(
                f"{operation_name} completed successfully",
                response_length=len(response_text),
            )
            return {
                "type": "generate",
                "success": True,
                "response": response_text,
                "content_type": "text",
            }
        except ValidationError as e:
            self._logger.error(f"Validation error in {operation_name}", error=str(e))
            raise
        except Exception as e:
            self._logger.critical(f"Unexpected error in {operation_name}", exc_info=True)
            raise ValidationError(f"Error in {operation_name}: {str(e)}")

    def generate_products(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        operation_name = "generate_products"
        self._logger.debug(f"{operation_name} initiated")
        try:
            validated_request = validate_product_gen(request_data)

            category_names = self.resolve_categories(validated_request.category)

            added_products = self.run_product_pipeline(
                quantity=validated_request.quantity,
                category_names=category_names,
                special_instructions=SPECIAL_INSTRUCTIONS_DEFAULT,
            )
            self._logger.info(
                f"{operation_name} completed successfully",
                product_count=len(added_products),
                categories=category_names,
            )
            return {
                "type": "generate_product",
                "success": True,
                "count": len(added_products),
                "products": added_products,
            }
        except ValidationError as e:
            self._logger.error(f"Validation error in {operation_name}", error=str(e))
            raise
        except Exception as e:
            self._logger.critical(f"Unexpected error in {operation_name}", exc_info=True)
            raise ValidationError(f"Error in {operation_name}: {str(e)}")

    def generate_scenario_products(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        operation_name = "generate_scenario_products"
        scenario = request_data.get("scenario")
        self._logger.debug(f"{operation_name} initiated", scenario=scenario)
        try:
            if not scenario:
                raise ValidationError("Scenario name is required")

            self.validate_scenario(scenario)
            self._logger.info(f"Processing scenario: {scenario}")

            category_names = self._category_service.select_random_categories()
            special_instructions = self.get_scenario_instructions(scenario)

            added_products = self.run_product_pipeline(
                quantity=10,
                category_names=category_names,
                special_instructions=special_instructions,
            )
            self._logger.info(
                f"{operation_name} completed successfully",
                scenario=scenario,
                product_count=len(added_products),
            )
            return {
                "type": "generate_scenario",
                "success": True,
                "scenario": scenario,
                "products": added_products,
            }
        except ValidationError as e:
            self._logger.error(f"Validation error in {operation_name}", error=str(e))
            raise
        except Exception as e:
            self._logger.critical(f"Unexpected error in {operation_name}", exc_info=True)
            raise ValidationError(f"Error in {operation_name}: {str(e)}")

    def run_product_pipeline(self, quantity: int, category_names: List[str], special_instructions: str = SPECIAL_INSTRUCTIONS_DEFAULT,) -> List[Dict[str, Any]]:

        prompt = self.build_product_generation_prompt(
            quantity=quantity,
            category_names=category_names,
            special_instructions=special_instructions,
        )
        response_text = self._provider.generate_response(prompt)
        products_data = AIResponseParser.parse_ai_response(response_text, self._logger)
        validated_products = validate_products_schema(products_data, self._logger)
        return self.add_products(validated_products)

    def resolve_categories(self, category: Optional[str]) -> List[str]:
        if category:
            names = self._category_service.validate_and_filter_categories(category)
            if names:
                return names
            self._logger.warning(
                f"No valid categories found in '{category}', selecting random categories"
            )
        return self._category_service.select_random_categories()

    def build_category_prompt(self, category_names: List[str]) -> str:
        categories_str = ", ".join(category_names)
        return CATEGORY_CONSTRAINT_PROMPT_TEMPLATE.format(category_name=categories_str)

    def build_product_generation_prompt(
        self,
        quantity: int,
        category_names: List[str],
        special_instructions: str = SPECIAL_INSTRUCTIONS_DEFAULT,
    ) -> str:
        category_prompt = self.build_category_prompt(category_names)
        return GENERATE_PRODUCTS_PROMPT.format(
            quantity=quantity,
            category_prompt=category_prompt,
            special_instructions=special_instructions,
        )

    def add_products(self, validated_products: List[GeneratedProductSchema]) -> List[Dict[str, Any]]:
        if not self._product_service:
            raise ValidationError("Product service is not configured for product persistence.")
        added_products = []
        for product in validated_products:
            product_dict = product.model_dump()
            try:
                added = self._product_service.create_product(product_dict)
                added_products.append(added)
                self._logger.debug(
                    "Product persisted successfully",
                    product_name=product_dict.get("name"),
                )
            except Exception as e:
                self._logger.error(
                    "Failed to persist product",
                    product_name=product_dict.get("name"),
                    error=str(e),
                )
                continue
        if not added_products:
            raise ValidationError("Failed to persist any generated products")
        return added_products

    def validate_scenario(self, scenario: str) -> None:
        valid_scenarios = {
            "Holiday Rush",
            "Flash Sale",
            "Back to School",
            "Premium Electronics",
            "Warehouse Overstock",
        }
        if scenario not in valid_scenarios:
            raise ValidationError(
                f"Invalid scenario '{scenario}'. Supported scenarios are: {', '.join(sorted(valid_scenarios))}"
            )

    def get_scenario_instructions(self, scenario: str) -> str:
        scenario_mapping = {
            "Holiday Rush": SCENARIO_HOLIDAY_RUSH,
            "Flash Sale": SCENARIO_FLASH_SALE,
            "Back to School": SCENARIO_BACK_TO_SCHOOL,
            "Premium Electronics": SCENARIO_PREMIUM_ELECTRONICS,
            "Warehouse Overstock": SCENARIO_WAREHOUSE_OVERSTOCK,
        }
        return scenario_mapping.get(scenario, SPECIAL_INSTRUCTIONS_DEFAULT)