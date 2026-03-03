from abc import ABC, abstractmethod
from typing import List, Optional

class ProductRepository(ABC):

    @abstractmethod
    def add(self, product: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, product_id: str) -> Optional[dict]:
        raise NotImplementedError

    @abstractmethod
    def list_paginated(self, page_size: int, after: Optional[str] = None, categories: Optional[List[str]] = None, search: Optional[str] = None,) -> dict:
        raise NotImplementedError

    @abstractmethod
    def update(self, product_id: str, changes: dict) -> Optional[dict]:
        raise NotImplementedError

    @abstractmethod
    def delete(self, product_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def barcode_exists(self, barcode: str, exclude_id: Optional[str] = None) -> bool:
        raise NotImplementedError
