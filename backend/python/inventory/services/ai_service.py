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
            category_names: List[str] = []
            
            if validated_request.category:
                category_names = self._category_service.validate_and_filter_categories(validated_request.category) 
                if not category_names:
                    self._logger.warning(
                        f"No valid categories found in '{validated_request.category}', selecting random categories"
                    )
                    category_names = self._category_service.select_random_categories()
            else:
                category_names = self._category_service.select_random_categories()
            
            category_prompt = self.build_category_prompt(category_names)
            prompt = GENERATE_PRODUCTS_PROMPT.format(
                quantity=validated_request.quantity,
                category_prompt=category_prompt,
            )
            response_text = self._provider.generate_response(prompt)
            products_data = AIResponseParser.parse_ai_response(response_text, self._logger)
            validated_products = validate_products_schema(products_data, self._logger)
            added_products = self.add_products(validated_products)
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

    def build_category_prompt(self, category_names: List[str]) -> str:
        categories_str = ", ".join(category_names)
        return CATEGORY_CONSTRAINT_PROMPT_TEMPLATE.format(category_name=categories_str)

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


