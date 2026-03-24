from pydantic import BaseModel, Field, field_validator, ValidationError as PydanticValidationError
from typing import List, Optional, Dict, Any
from .validators import validate_price, validate_quantity, validate_minimum_stock_level, validate_generate_quantity
from .exceptions import ValidationError


class GeneratedProductSchema(BaseModel):
    name: str = Field(..., min_length=1, description="Product name")
    price: float = Field(..., gt=0.0, description="Product price")
    quantity: int = Field(..., ge=0, description="Stock quantity")
    description: str = Field(default="", description="Product description")
    barcode: Optional[str] = Field(default=None, description="Product barcode")
    category: str = Field(default="", description="Comma-separated category names")
    brand: str = Field(default="", description="Product brand")
    minimum_stock_level: int = Field(default=0, ge=0, description="Minimum stock level")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
        return v

    @field_validator('price')
    @classmethod
    def validate_price_field(cls, v: float) -> float:
        return float(validate_price(v))

    @field_validator('quantity')
    @classmethod
    def validate_quantity_field(cls, v: int) -> int:
        return validate_quantity(v)

    @field_validator('minimum_stock_level')
    @classmethod
    def validate_minimum_stock_level_field(cls, v: int) -> int:
        return validate_minimum_stock_level(v)

    class Config:
        validate_assignment = True
        str_strip_whitespace = True


class GeneratedProductListSchema(BaseModel):
    products: List[GeneratedProductSchema]
    class Config:
        validate_assignment = True


class TextGenerationRequestSchema(BaseModel):
    prompt: str = Field(..., min_length=1, description="Generation prompt")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_output_tokens: Optional[int] = Field(None, gt=0)
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0)
    top_k: Optional[int] = Field(None, gt=0)
    top_sequences: Optional[int] = Field(None, gt=0)

    class Config:
        validate_assignment = True
        str_strip_whitespace = True


class ProductGenerationRequestSchema(BaseModel):
    quantity: int = Field(..., ge=1, le=50, description="Number of products to generate")
    category: Optional[str] = Field(None, description="Comma-separated category names")
    @field_validator('quantity')
    @classmethod
    def validate_quantity_field(cls, v: int) -> int:
        return validate_generate_quantity(v)

    class Config:
        validate_assignment = True


def validate_text_gen(request_data: Dict[str, Any]) -> TextGenerationRequestSchema:
    try:
        return TextGenerationRequestSchema(**request_data)
    except PydanticValidationError as e:
        raise ValidationError(f"Invalid text generation request: {str(e)}")


def validate_product_gen(request_data: Dict[str, Any]) -> ProductGenerationRequestSchema:
    try:
        return ProductGenerationRequestSchema(**request_data)
    except PydanticValidationError as e:
        raise ValidationError(f"Invalid product generation request: {str(e)}")


def extract_config(request: TextGenerationRequestSchema) -> Dict[str, Any]:
    config = {}
    optional_fields = [
        "temperature",
        "max_output_tokens",
        "top_p",
        "top_k",
        "top_sequences",
    ]
    for field in optional_fields:
        value = getattr(request, field, None)
        if value is not None:
            config[field] = value
    return config


def validate_products_schema(products_data: List[Dict[str, Any]], logger=None) -> List[GeneratedProductSchema]:
    validated_products: List[GeneratedProductSchema] = []
    
    for idx, product_data in enumerate(products_data):
        try:
            validated_product = GeneratedProductSchema(**product_data)
            validated_products.append(validated_product)
        except PydanticValidationError as e:
            if logger:
                logger.warning(
                    f"Product at index {idx} failed validation",
                    product_data=product_data,
                    error=str(e),
                )
    
    if not validated_products:
        raise ValidationError(
            "Failed to validate any products from AI response"
        )
    
    if len(validated_products) < len(products_data) and logger:
        logger.warning(
            "Some products were skipped due to validation errors",
            total=len(products_data),
            valid=len(validated_products),
        )
    
    return validated_products
