from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, FloatField, Value
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from products.models import Product

from .forms import AddressForm, ProfileForm, RegistrationForm
from .models import Address, Notification, WishlistItem
from .services import get_or_create_customer


def register(request):
    if request.user.is_authenticated:
        return redirect("index")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        customer = form.save()
        login(request, customer.user)
        messages.success(request, "Your account has been created successfully.")
        return redirect("index")
    return render(request, "registration/register.html", {"form": form})


def safe_next_url(request, fallback="index"):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}):
        return next_url
    return fallback


@login_required
def wishlist(request):
    items = WishlistItem.objects.filter(user=request.user).select_related("product").annotate(
        rating_average=Coalesce(Avg("product__reviews__rating"), Value(0.0), output_field=FloatField()),
        review_count=Count("product__reviews", distinct=True),
    )
    return render(request, "customers/wishlist.html", {"wishlist_items": items, "active_account_page": "wishlist"})


@login_required
def wishlist_toggle(request, pk):
    if request.method != "POST":
        return redirect("product_detail", pk=pk)
    product = get_object_or_404(Product, pk=pk)
    item = WishlistItem.objects.filter(user=request.user, product=product).first()
    if item:
        item.delete()
        messages.info(request, f"{product.name} was removed from your wishlist.")
    else:
        WishlistItem.objects.get_or_create(user=request.user, product=product)
        messages.success(request, f"{product.name} was added to your wishlist.")
    return redirect(safe_next_url(request, "wishlist"))


@login_required
def wishlist_remove(request, pk):
    if request.method == "POST":
        item = get_object_or_404(WishlistItem, pk=pk, user=request.user)
        product_name = item.product.name
        item.delete()
        messages.info(request, f"{product_name} was removed from your wishlist.")
    return redirect(safe_next_url(request, "wishlist"))


@login_required
def wishlist_move_to_cart(request, pk):
    if request.method != "POST":
        return redirect(safe_next_url(request, "wishlist"))
    item = get_object_or_404(WishlistItem.objects.select_related("product"), pk=pk, user=request.user)
    product = item.product
    if not product.is_in_stock:
        messages.error(request, f"{product.name} is currently out of stock.")
        return redirect(safe_next_url(request, "wishlist"))
    payload = {
        "product_id": product.id,
        "name": product.name,
        "price": str(product.price),
        "image": product.image.url if product.image else "",
        "stock_quantity": product.stock_quantity,
    }
    item.delete()
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"success": True, "product": payload})
    request.session["pending_cart_item"] = payload
    messages.success(request, f"{product.name} was moved to your bag.")
    return redirect("cart")


@login_required
def notifications(request):
    return render(request, "customers/notifications.html", {"notifications": request.user.notifications.all()})


@login_required
def notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if request.method == "POST":
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    return redirect(notification.link or "notifications")


@login_required
def notifications_mark_all_read(request):
    if request.method == "POST":
        request.user.notifications.filter(is_read=False).update(is_read=True)
        messages.success(request, "All notifications marked as read.")
    return redirect("notifications")


@login_required
def dashboard(request):
    # The former dashboard put every account panel on one document.  Keep its
    # established URL as a bookmark-compatible entry point, but direct users
    # to the first separate account page.
    return redirect("account_profile")


@login_required
def account_profile(request):
    customer = get_or_create_customer(request.user)
    form = ProfileForm(instance=customer, initial={"first_name": request.user.first_name, "last_name": request.user.last_name, "email": request.user.email})
    return render(request, "customers/account_profile.html", {"profile_form": form, "active_account_page": "profile"})


@login_required
def account_orders(request):
    from orders.models import Order
    return render(request, "customers/account_orders.html", {"orders": Order.objects.filter(customer=get_or_create_customer(request.user)).prefetch_related("items__product"), "active_account_page": "orders"})


@login_required
def account_wishlist(request):
    return render(request, "customers/account_wishlist.html", {"wishlist_items": WishlistItem.objects.filter(user=request.user).select_related("product"), "active_account_page": "wishlist"})


@login_required
def account_addresses(request):
    return render(request, "customers/account_addresses.html", {"addresses": get_or_create_customer(request.user).addresses.all(), "active_account_page": "addresses"})


@login_required
def account_location(request):
    return render(request, "customers/account_location.html", {"addresses": get_or_create_customer(request.user).addresses.all(), "active_account_page": "location"})


@login_required
def account_coupons(request):
    from orders.models import Coupon
    return render(request, "customers/account_coupons.html", {"coupons": Coupon.objects.filter(is_active=True), "active_account_page": "coupons"})


@login_required
def account_settings(request):
    return render(request, "customers/account_settings.html", {"active_account_page": "settings"})


@login_required
def profile_update(request):
    if request.method != "POST": return redirect("account_profile")
    form = ProfileForm(request.POST, instance=get_or_create_customer(request.user))
    if form.is_valid():
        form.save(); messages.success(request, "Profile updated.")
    else: messages.error(request, "Please correct your profile details.")
    return redirect("account_profile")


@login_required
def address_save(request, pk=None):
    if request.method != "POST": return redirect("account_addresses")
    customer = get_or_create_customer(request.user)
    instance = get_object_or_404(Address, pk=pk, customer=customer) if pk else None
    form = AddressForm(request.POST, instance=instance)
    if form.is_valid():
        address = form.save(commit=False); address.customer = customer
        if address.is_default: Address.objects.filter(customer=address.customer).exclude(pk=address.pk).update(is_default=False)
        address.save(); messages.success(request, "Address saved.")
    else: messages.error(request, "Please correct the address details.")
    return redirect(safe_next_url(request, "account_addresses"))


@login_required
def address_delete(request, pk):
    if request.method == "POST":
        get_object_or_404(Address, pk=pk, customer=get_or_create_customer(request.user)).delete(); messages.success(request, "Address removed.")
    return redirect(safe_next_url(request, "account_addresses"))
