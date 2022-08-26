from typing import List, Set

from pydantic import BaseModel


class Product(BaseModel):
    id: str
    purchase_note: str = ""
    files: List[str] = []


class Order(BaseModel):
    id: str
    total: float
    email: str
    first_name: str
    last_name: str
    total_files: Set[str] = set()
    status: bool = False
    products: List[Product] = []
