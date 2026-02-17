from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional


@dataclass
class Product:
    id: int
    name: str
    price: str 
    quantity: int
    description: str = ''
    barcode: str = ''
    category: str = ''
    brand: str = ''
    minimum_stock_level: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Product':
        return cls(
            id=data['id'],
            name=data['name'],
            price=data['price'],
            quantity=data['quantity'],
            description=data.get('description', ''),
            barcode=data.get('barcode', ''),
            category=data.get('category', ''),
            brand=data.get('brand', ''),
            minimum_stock_level=data.get('minimum_stock_level', 0),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at'),
        )
    
    def __repr__(self) -> str:
        return f"Product(id={self.id}, name='{self.name}', barcode='{self.barcode}')"
