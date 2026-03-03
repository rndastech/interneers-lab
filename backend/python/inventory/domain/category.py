from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Category:
    title: str
    description: str
    id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_deleted: bool = False

    def to_dict(self) -> dict:
        data = asdict(self)
        if data.get('id') is None:
            data.pop('id', None)
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Category':
        return cls(
            id=data.get('id'),
            title=data['title'],
            description=data['description'],
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at'),
            is_deleted=data.get('is_deleted', False),
        )
    
    def __repr__(self) -> str:
        return f"Category(id={self.id}, title='{self.title}')"
