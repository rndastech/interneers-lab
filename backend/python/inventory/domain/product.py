from dataclasses import dataclass, asdict
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass
class Product:
    name: str
    price: Decimal
    quantity: int
    id: Optional[str] = None
    description: str = ''
    barcode: str = ''
    category: str = ''
    brand: str = ''
    minimum_stock_level: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_deleted: bool = False

    def to_dict(self) -> dict:
        data = asdict(self)
        if data.get('id') is None:
            data.pop('id', None)
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Product':
        return cls(
            id=data.get('id'),
            name=data['name'],
            price=Decimal(str(data['price'])),
            quantity=data['quantity'],
            description=data.get('description', ''),
            barcode=data.get('barcode', ''),
            category=data.get('category', ''),
            brand=data.get('brand', ''),
            minimum_stock_level=data.get('minimum_stock_level', 0),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at'),
            is_deleted=data.get('is_deleted', False),
        )
    
    def __repr__(self) -> str:
        return f"Product(id={self.id}, name='{self.name}', barcode='{self.barcode}')"
