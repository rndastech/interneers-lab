from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class ProductLogger(ABC):
    @abstractmethod
    def debug(self, message: str, **context: Any) -> None:
        pass

    @abstractmethod
    def info(self, message: str, **context: Any) -> None:
        pass

    @abstractmethod
    def warning(self, message: str, **context: Any) -> None:
        pass

    @abstractmethod
    def error(self, message: str, **context: Any) -> None:
        pass

    @abstractmethod
    def critical(self, message: str, **context: Any) -> None:
        pass
