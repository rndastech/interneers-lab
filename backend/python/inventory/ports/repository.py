from abc import ABC, abstractmethod
from typing import Optional

class ProductRepository(ABC):

    @abstractmethod
    def next_id(self) -> int:
        raise NotImplementedError

    @abstractmethod
    def add(self, product: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, product_id: int) -> Optional[dict]:
        raise NotImplementedError

    @abstractmethod
    def list_all(self) -> list:
        raise NotImplementedError

    @abstractmethod
    def update(self, product_id: int, product: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def delete(self, product_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def barcode_exists(self, barcode: str, exclude_id: Optional[int] = None) -> bool:
        raise NotImplementedError
