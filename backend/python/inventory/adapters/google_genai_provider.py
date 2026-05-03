import os
import logging
from functools import lru_cache
from typing import Any, Tuple
from dotenv import load_dotenv
from google import genai
from google.genai import types
from inventory.ports.ai_provider import AIProvider
from inventory.domain.exceptions import ValidationError
load_dotenv()

class GoogleGenAIProvider(AIProvider):

    DEFAULT_MODEL = "gemini-2.0-flash"
    SYSTEM_INSTRUCTION = "You are a helpful assistant."

    def __init__(self) -> None:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValidationError("GOOGLE_API_KEY not found in environment variables")
        self._client = genai.Client(api_key=api_key)
        self._model = os.getenv("GOOGLE_MODEL", self.DEFAULT_MODEL)

    def generate_response(self, prompt: str, **kwargs: Any) -> Tuple[str, dict]:
        config = types.GenerateContentConfig(
            system_instruction=self.SYSTEM_INSTRUCTION,
            **kwargs,
        )
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=config,
            )
        except Exception as e:
            raise ValidationError(f"Google GenAI API error: {e}") from e
        text = self._extract_text(response)
        if not text:
            raise ValidationError("No text content received from Google GenAI API")
        usage = self._extract_usage(response)
        return text, usage

    @staticmethod
    def _extract_text(response: types.GenerateContentResponse) -> str:
        try:
            if response.text:
                return response.text.strip()
        except (AttributeError, ValueError):
            pass
        for candidate in getattr(response, "candidates", []) or []:
            for part in getattr(candidate.content, "parts", []) or []:
                text = getattr(part, "text", None)
                if text:
                    return text.strip()
        return ""

    @staticmethod
    def _extract_usage(response: types.GenerateContentResponse) -> dict:
        metadata = getattr(response, "usage_metadata", None)
        if metadata is None:
            return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        return {
            "prompt_tokens": getattr(metadata, "prompt_token_count", 0) or 0,
            "completion_tokens": getattr(metadata, "candidates_token_count", 0) or 0,
            "total_tokens": getattr(metadata, "total_token_count", 0) or 0,
        }

@lru_cache(maxsize=1)
def get_google_genai_provider() -> GoogleGenAIProvider:
    return GoogleGenAIProvider()