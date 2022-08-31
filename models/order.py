from typing import List, Set

from pydantic import BaseModel


class ProductFile(BaseModel):
    file_name: str = ""
    file_size: int = 0


class Product(BaseModel):
    name: str = ""
    purchase_note: str = ""


class Order(BaseModel):
    id: str
    total: float
    email: str
    first_name: str
    last_name: str
    total_files: List[ProductFile] = []
    status: bool = False
    products: List[Product] = []
