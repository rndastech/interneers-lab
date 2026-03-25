from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class AIProvider(ABC):
    @abstractmethod
    def generate_response(self, prompt: str, **kwargs: Any) -> str:
        pass
