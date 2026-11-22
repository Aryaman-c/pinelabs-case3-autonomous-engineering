import pytest
from cart.models import CartItem
from cart.services import CartService


@pytest.fixture
def service():
    return CartService()


def test_create_cart(service):
    cart = service.create_cart("test-cart")
    assert cart.cart_id == "test-cart"
    assert cart.items == []


def test_add_item_and_total(service):
    service.create_cart("c1")
    service.add_item("c1", CartItem("p1", "Item 1", 10.0, 2))
    assert service.get_total("c1") == 20.0
