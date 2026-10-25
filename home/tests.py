from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from home.models import Address, CartItem, Order, OrderItem, Product


class StoreFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="shopper", password="strong-test-password")
        self.product = Product.objects.create(name="Linen shirt", price=Decimal("1499.00"), stock=3)
        self.address = Address.objects.create(
            user=self.user,
            line1="12 Market Road",
            city="Jaipur",
            state="Rajasthan",
            zip_code="302001",
        )
        self.client.force_login(self.user)

    def test_cart_mutations_require_post(self):
        add_url = reverse("add_to_cart", args=[self.product.id])
        self.assertEqual(self.client.get(add_url).status_code, 405)
        self.assertEqual(CartItem.objects.count(), 0)

        item = CartItem.objects.create(user=self.user, product=self.product)
        self.assertEqual(self.client.get(reverse("remove_from_cart", args=[item.id])).status_code, 405)
        self.assertTrue(CartItem.objects.filter(id=item.id).exists())
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)

    def test_store_and_customer_pages_render(self):
        CartItem.objects.create(user=self.user, product=self.product)
        self.assertEqual(self.client.get(reverse("home")).status_code, 200)
        self.assertEqual(self.client.get(reverse("product_list")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("product_detail", args=[self.product.slug])).status_code,
            200,
        )
        self.assertEqual(self.client.get(reverse("cart")).status_code, 200)
        self.assertEqual(self.client.get(reverse("checkout")).status_code, 200)
        self.assertEqual(self.client.get(reverse("profile_settings")).status_code, 200)
        self.assertEqual(self.client.get(reverse("account_settings")).status_code, 200)
        self.assertEqual(self.client.get(reverse("saved_addresses")).status_code, 200)

    def test_add_to_cart_respects_available_stock(self):
        url = reverse("add_to_cart", args=[self.product.id])
        self.assertEqual(self.client.post(url).status_code, 302)
        self.product.stock = 1
        self.product.save(update_fields=["stock"])
        self.client.post(url)
        self.assertEqual(CartItem.objects.get(user=self.user, product=self.product).quantity, 1)

    def test_update_quantity_cannot_exceed_stock(self):
        item = CartItem.objects.create(user=self.user, product=self.product, quantity=1)
        self.client.post(reverse("update_cart", args=[item.id]), {"quantity": "4"})
        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)

    def test_checkout_returns_to_bag_when_stock_is_no_longer_available(self):
        CartItem.objects.create(user=self.user, product=self.product, quantity=2)
        self.product.stock = 1
        self.product.save(update_fields=["stock"])

        response = self.client.get(reverse("checkout"))

        self.assertRedirects(response, reverse("cart"))
        self.assertContains(self.client.get(reverse("cart")), "Fix your bag to continue")

    def test_checkout_returns_to_bag_when_a_product_was_deactivated(self):
        CartItem.objects.create(user=self.user, product=self.product)
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])

        response = self.client.get(reverse("checkout"))

        self.assertRedirects(response, reverse("cart"))
        cart_response = self.client.get(reverse("cart"))
        self.assertContains(cart_response, "No longer available")
        self.assertNotContains(cart_response, "Continue to checkout")

    def test_order_requires_an_address_owned_by_the_customer(self):
        CartItem.objects.create(user=self.user, product=self.product)
        other_user = User.objects.create_user(username="another", password="strong-test-password")
        other_address = Address.objects.create(
            user=other_user,
            line1="Other street",
            city="Jaipur",
            state="Rajasthan",
            zip_code="302002",
        )

        self.client.post(reverse("place_order"), {"address": other_address.id})

        self.assertEqual(Order.objects.count(), 0)
        self.assertTrue(CartItem.objects.filter(user=self.user).exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)

    def test_order_records_items_and_reserves_stock_atomically(self):
        CartItem.objects.create(user=self.user, product=self.product, quantity=2)

        response = self.client.post(reverse("place_order"), {"address": self.address.id})

        order = Order.objects.get(user=self.user)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("order_success", args=[order.id]))
        self.assertEqual(order.total_price, Decimal("2998.00"))
        self.assertEqual(order.status, "requested")
        self.assertEqual(order.get_status_display(), "Request received")
        self.assertEqual(OrderItem.objects.get(order=order).product_name, "Linen shirt")
        self.assertEqual(order.shipping_line1, self.address.line1)
        self.assertEqual(order.shipping_zip_code, self.address.zip_code)
        self.address.line1 = "Changed after checkout"
        self.address.save(update_fields=["line1"])
        self.address.delete()
        order.refresh_from_db()
        self.assertIsNone(order.address)
        self.assertEqual(order.shipping_line1, "12 Market Road")
        self.assertContains(
            self.client.get(reverse("order_success", args=[order.id])),
            "12 Market Road",
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 1)
        self.assertFalse(CartItem.objects.filter(user=self.user).exists())

    def test_order_does_not_partially_reserve_when_stock_is_short(self):
        CartItem.objects.create(user=self.user, product=self.product, quantity=4)

        self.client.post(reverse("place_order"), {"address": self.address.id})

        self.assertEqual(Order.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)
        self.assertTrue(CartItem.objects.filter(user=self.user).exists())
