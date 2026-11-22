from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CartItem:
    product_id: str
    name: str
    price: float
    quantity: int = 1

    @property
    def subtotal(self) -> float:
        return self.price * self.quantity


@dataclass
class Cart:
    cart_id: str
    items: list[CartItem] = field(default_factory=list)
