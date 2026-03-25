from abc import ABC, abstractmethod
from typing import List, Optional

class CategoryRepository(ABC):

    @abstractmethod
    def add(self, category: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, category_id: str) -> Optional[dict]:
        raise NotImplementedError

    @abstractmethod
    def list_paginated(self, page_size: int, after: Optional[str] = None, search: Optional[str] = None) -> dict:
        raise NotImplementedError

    @abstractmethod
    def update(self, category_id: str, changes: dict) -> Optional[dict]:
        raise NotImplementedError

    @abstractmethod
    def delete(self, category_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def title_exists(self, title: str, exclude_id: Optional[str] = None) -> bool:
        raise NotImplementedError

    @abstractmethod
    def count_products_per_category(self, titles: List[str]) -> dict:
        raise NotImplementedError
