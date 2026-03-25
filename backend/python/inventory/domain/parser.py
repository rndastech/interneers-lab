import json
from typing import Dict, Any, List
from inventory.domain.exceptions import ValidationError
from inventory.ports.logger import ProductLogger


class AIResponseParser:
    @staticmethod
    def parse_ai_response(response_text: str, logger: ProductLogger) -> List[Dict[str, Any]]:
        cleaned_response = AIResponseParser.clean_markdown_formatting(response_text)
        try:
            products_data = json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse AI response as JSON",
                response_preview=cleaned_response[:200],
                error=str(e),
            )
            raise ValidationError(f"Invalid JSON in AI response: {str(e)}")
        
        if not isinstance(products_data, list):
            raise ValidationError("AI response must be a JSON array of products")
        if not products_data:
            raise ValidationError("AI returned empty product list")
        
        return products_data

    @staticmethod
    def clean_markdown_formatting(response_text: str) -> str:
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:].strip()
            if text.endswith("```"):
                text = text[:-3].strip()
        elif text.startswith("```"):
            text = text[3:].strip()
            if text.endswith("```"):
                text = text[:-3].strip()
        
        return text
