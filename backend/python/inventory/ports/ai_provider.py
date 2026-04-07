from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Tuple


class AIProvider(ABC):
    @abstractmethod
    def generate_response(self, prompt: str, **kwargs: Any) -> Tuple[str, dict]:
        pass
