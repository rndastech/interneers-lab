from __future__ import annotations

import importlib
import os
from typing import Any

from inventory.domain.exceptions import ValidationError
from inventory.ports.ai_provider import AIProvider
from inventory.ports.logger import ProductLogger


class LangChainGoogleGenAIAdapter:

    def __init__(self, ai_provider: AIProvider, logger: ProductLogger) -> None:
        self._ai_provider = ai_provider
        self._logger = logger
        self._model = os.getenv("GOOGLE_MODEL", "gemini-2.0-flash")
        self._api_key = os.getenv("GOOGLE_API_KEY", "")

    def generate_grounded_answer(
        self,
        *,
        question: str,
        context: str,
        system_instruction: str,
    ) -> tuple[str, dict[str, int]]:
        if not question.strip():
            raise ValidationError("Question must not be empty")

        if self._api_key:
            try:
                return self._generate_with_langchain(
                    question=question,
                    context=context,
                    system_instruction=system_instruction,
                )
            except Exception as e:
                self._logger.warning(
                    "LangChain generation failed; falling back to AIProvider",
                    error=str(e),
                )

        prompt = self._fallback_prompt(
            question=question,
            context=context,
            system_instruction=system_instruction,
        )
        text, usage = self._ai_provider.generate_response(prompt)
        return text, self._normalize_usage(usage)

    def _generate_with_langchain(
        self,
        *,
        question: str,
        context: str,
        system_instruction: str,
    ) -> tuple[str, dict[str, int]]:
        lc_prompt_module = importlib.import_module("langchain_core.prompts")
        lc_output_module = importlib.import_module("langchain_core.output_parsers")
        lc_google_module = importlib.import_module("langchain_google_genai")

        chat_prompt_template = getattr(lc_prompt_module, "ChatPromptTemplate")
        str_output_parser = getattr(lc_output_module, "StrOutputParser")
        chat_google_model = getattr(lc_google_module, "ChatGoogleGenerativeAI")

        prompt = chat_prompt_template.from_messages(
            [
                ("system", "{system_instruction}"),
                (
                    "human",
                    "Context:\n{context}\n\nQuestion:\n{question}\n\n"
                    "Answer using only the provided context. If context is insufficient, say so clearly.",
                ),
            ]
        )

        llm = chat_google_model(
            model=self._model,
            google_api_key=self._api_key,
            temperature=0.2,
        )
        chain = prompt | llm | str_output_parser()

        text = chain.invoke(
            {
                "system_instruction": system_instruction,
                "context": context,
                "question": question,
            }
        )
        answer = (text or "").strip()
        if not answer:
            raise ValidationError("LangChain model returned an empty answer")
        return answer, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    @staticmethod
    def _fallback_prompt(*, question: str, context: str, system_instruction: str) -> str:
        return (
            f"{system_instruction}\n\n"
            f"Context:\n{context}\n\n"
            f"Question:\n{question}\n\n"
            "Answer using only the provided context. "
            "If the answer is not in context, explicitly say you don't have enough information."
        )

    @staticmethod
    def _normalize_usage(usage: Any) -> dict[str, int]:
        if not isinstance(usage, dict):
            return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        return {
            "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
            "total_tokens": int(usage.get("total_tokens", 0) or 0),
        }
