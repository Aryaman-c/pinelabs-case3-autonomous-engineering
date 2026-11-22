from typing import Optional
from cart.models import Cart, CartItem


class CartService:
    def __init__(self):
        self._carts: dict[str, Cart] = {}

    def create_cart(self, cart_id: str) -> Cart:
        cart = Cart(cart_id=cart_id)
        self._carts[cart_id] = cart
        return cart

    def get_cart(self, cart_id: str) -> Optional[Cart]:
        return self._carts.get(cart_id)

    def add_item(self, cart_id: str, item: CartItem) -> Cart:
        cart = self._carts[cart_id]
        cart.items.append(item)
        return cart

    def get_total(self, cart_id: str) -> float:
        cart = self._carts[cart_id]
        return sum(item.subtotal for item in cart.items)
