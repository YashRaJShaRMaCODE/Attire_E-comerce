from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, UserCreationForm
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render

from home.models import (
    Address,
    CartItem,
    Category,
    Contact,
    Feedback,
    Order,
    OrderItem,
    Product,
)
from home.forms import AddressForm, ProfileForm


def index(request):
    products = Product.objects.filter(is_active=True)[:6]
    categories = Category.objects.all()
    context = {"products": products, "categories": categories}
    return render(request, "index.html", context)


def about(request):
    return render(request, "about.html")


def services(request):
    return render(request, "services.html")


def product_list(request):
    products = Product.objects.filter(is_active=True).select_related("category").order_by("name", "id")
    category_slug = request.GET.get("category", "")[:120]
    query = request.GET.get("q", "").strip()[:100]

    if category_slug:
        products = products.filter(category__slug=category_slug)
    if query:
        products = products.filter(Q(name__icontains=query) | Q(description__icontains=query))

    categories = Category.objects.all()
    page = Paginator(products, 12).get_page(request.GET.get("page"))
    return render(request, "product_list.html", {
        "page": page,
        "products": page.object_list,
        "categories": categories,
        "query": query,
        "selected_category": category_slug or "",
    })


def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    return render(request, "product_detail.html", {"product": product})


def contact(request):
    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        message = request.POST.get("message")

        Contact.objects.create(name=name, email=email, message=message)
        messages.success(request, "Thanks for reaching out! We'll get back to you soon.")

    return render(request, "contact.html")


def feedback(request):
    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        message = request.POST.get("message")

        Feedback.objects.create(name=name, email=email, message=message)
        messages.success(request, "Thank you for your feedback!")

    return render(request, "feedback.html")


def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Account created successfully. Welcome!")
            return redirect("home")
    else:
        form = UserCreationForm()

    return render(request, "register.html", {"form": form})


def user_login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect("home")
        else:
            messages.error(request, "Invalid username or password")

    return render(request, "login.html")


@require_POST
def user_logout(request):
    logout(request)
    return redirect("login")


@login_required
def cart(request):
    cart_items = CartItem.objects.filter(user=request.user).select_related("product")
    total_price = sum((item.total_price for item in cart_items), Decimal("0"))
    has_unavailable_items = any(
        not item.product.is_active or item.quantity > item.product.stock
        for item in cart_items
    )
    return render(request, "cart.html", {
        "cart_items": cart_items,
        "total_price": total_price,
        "has_unavailable_items": has_unavailable_items,
    })


@login_required
@require_POST
def add_to_cart(request, product_id):
    with transaction.atomic():
        product = get_object_or_404(Product.objects.select_for_update(), id=product_id, is_active=True)
        if product.stock < 1:
            messages.error(request, "This item is out of stock.")
            return redirect("product_detail", slug=product.slug)
        cart_item, created = CartItem.objects.get_or_create(user=request.user, product=product)
        if not created and cart_item.quantity >= product.stock:
            messages.error(request, "Your cart already has all available stock.")
        else:
            if not created:
                cart_item.quantity += 1
                cart_item.save(update_fields=["quantity"])
            messages.success(request, f"{product.name} added to your bag.")
    return redirect("cart")


@login_required
@require_POST
def update_cart(request, item_id):
    cart_item = get_object_or_404(CartItem, id=item_id, user=request.user)
    try:
        quantity = int(request.POST.get("quantity", ""))
    except ValueError:
        quantity = 0

    if quantity < 1 or quantity > cart_item.product.stock:
        messages.error(request, "Choose a quantity within the available stock.")
    else:
        cart_item.quantity = quantity
        cart_item.save(update_fields=["quantity"])
        messages.success(request, "Bag updated.")

    return redirect("cart")


@login_required
@require_POST
def remove_from_cart(request, item_id):
    cart_item = get_object_or_404(CartItem, id=item_id, user=request.user)
    cart_item.delete()
    messages.success(request, "Item removed from cart.")
    return redirect("cart")


@login_required
def checkout(request):
    cart_items = list(CartItem.objects.filter(user=request.user).select_related("product"))
    if not cart_items:
        messages.error(request, "Your cart is empty.")
        return redirect("cart")
    if any(not item.product.is_active or item.quantity > item.product.stock for item in cart_items):
        messages.error(request, "An item in your bag is unavailable or has less stock now. Review your bag before checkout.")
        return redirect("cart")

    total_price = sum((item.total_price for item in cart_items), Decimal("0"))
    addresses = Address.objects.filter(user=request.user)
    return render(request, "checkout.html", {"cart_items": cart_items, "total_price": total_price, "addresses": addresses})


@login_required
@require_POST
def place_order(request):
    try:
        address_id = int(request.POST.get("address", ""))
    except (TypeError, ValueError):
        address_id = 0
    if not Address.objects.filter(id=address_id, user=request.user).exists():
        messages.error(request, "Choose one of your saved addresses to continue.")
        return redirect("checkout")

    try:
        with transaction.atomic():
            address = Address.objects.select_for_update().get(id=address_id, user=request.user)
            cart_items = list(
                CartItem.objects.select_for_update()
                .filter(user=request.user)
                .order_by("id")
            )
            if not cart_items:
                messages.error(request, "Your bag is empty.")
                return redirect("cart")

            products = {
                product.id: product
                for product in Product.objects.select_for_update()
                .filter(id__in=[item.product_id for item in cart_items])
                .order_by("id")
            }
            order_items = []
            for item in cart_items:
                product = products.get(item.product_id)
                if not product or not product.is_active:
                    raise ValueError
                updated = Product.objects.filter(
                    id=product.id, is_active=True, stock__gte=item.quantity
                ).update(stock=F("stock") - item.quantity)
                if not updated:
                    raise ValueError
                order_items.append(OrderItem(
                    product=product,
                    product_name=product.name,
                    price=product.price,
                    quantity=item.quantity,
                ))

            total_price = sum(
                (item.price * item.quantity for item in order_items), Decimal("0")
            )
            order = Order.objects.create(
                user=request.user,
                address=address,
                shipping_line1=address.line1,
                shipping_line2=address.line2,
                shipping_city=address.city,
                shipping_state=address.state,
                shipping_zip_code=address.zip_code,
                total_price=total_price,
            )
            OrderItem.objects.bulk_create([
                OrderItem(order=order, **{
                    "product": item.product,
                    "product_name": item.product_name,
                    "price": item.price,
                    "quantity": item.quantity,
                })
                for item in order_items
            ])
            CartItem.objects.filter(user=request.user).delete()
    except ValueError:
        messages.error(request, "An item changed or sold out. Review your bag and try again.")
        return redirect("cart")

    messages.success(request, "Your order request has been recorded.")
    return redirect("order_success", order_id=order.id)


@login_required
def order_success(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, "order_success.html", {"order": order})


@login_required
def my_account(request):
    recent_orders = Order.objects.filter(user=request.user).order_by("-created_at")[:5]
    return render(request, "my_account.html", {"recent_orders": recent_orders})


@login_required
def profile_settings(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile updated successfully.")
        return redirect("profile_settings")

    return render(request, "profile_settings.html", {"form": form})


@login_required
def account_settings(request):
    form = PasswordChangeForm(user=request.user, data=request.POST or None)
    for name, field in form.fields.items():
        field.widget.attrs["class"] = "form-control"
        field.widget.attrs["autocomplete"] = "current-password" if name == "old_password" else "new-password"
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Password updated successfully.")
        return redirect("account_settings")

    return render(request, "account_settings.html", {"form": form})


@login_required
def my_orders(request):
    orders = Order.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "my_orders.html", {"orders": orders})


@login_required
def purchase_history(request):
    orders = Order.objects.filter(user=request.user, status="delivered").order_by("-created_at")
    return render(request, "purchase_history.html", {"orders": orders})


@login_required
def saved_addresses(request):
    form = AddressForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        address = form.save(commit=False)
        address.user = request.user
        address.save()
        messages.success(request, "Address saved.")
        return redirect("saved_addresses")

    addresses = Address.objects.filter(user=request.user)
    return render(request, "saved_addresses.html", {"addresses": addresses, "form": form})


@login_required
@require_POST
def delete_address(request, address_id):
    address = get_object_or_404(Address, id=address_id, user=request.user)
    address.delete()
    messages.success(request, "Address removed.")
    return redirect("saved_addresses")


@login_required
def settings(request):
    return render(request, "settings.html")
