import json
import secrets
from collections import defaultdict
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from products.models import Product
from customers.models import Notification
from customers.models import Address
from customers.services import get_or_create_customer

from .models import Coupon, CouponRedemption, EMIPlan, Order, OrderItem


@staff_member_required
def download_order_export(request):
    """Download only the supplied order workbook as a real XLSX response."""
    from .services import WORKBOOK_PATH

    if not WORKBOOK_PATH.is_file():
        raise Http404(f"Order workbook is unavailable: {WORKBOOK_PATH}")
    return FileResponse(
        WORKBOOK_PATH.open("rb"),
        as_attachment=True,
        filename=WORKBOOK_PATH.name,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def coupon_for_checkout(code, user, subtotal, delivery_charge):
    if not code:
        return None, Decimal("0.00"), ""
    coupon = Coupon.objects.select_for_update().filter(code__iexact=code.strip()).first()
    if not coupon:
        return None, Decimal("0.00"), "That coupon code is invalid."
    now = timezone.now()
    if not coupon.is_active or coupon.starts_at > now or coupon.expires_at <= now:
        return None, Decimal("0.00"), "That coupon is not currently active."
    if subtotal < coupon.minimum_order_value:
        return None, Decimal("0.00"), f"This coupon requires an order of at least ₹{coupon.minimum_order_value}."
    if coupon.usage_limit is not None and coupon.times_used >= coupon.usage_limit:
        return None, Decimal("0.00"), "This coupon has reached its usage limit."
    used_by_user = CouponRedemption.objects.filter(coupon=coupon, user=user).count()
    if used_by_user >= coupon.per_user_limit:
        return None, Decimal("0.00"), "You have already used this coupon."
    if coupon.new_users_only and Order.objects.filter(customer__user=user).exclude(status=Order.Status.CANCELLED).exists():
        return None, Decimal("0.00"), "This offer is only available for new customers."
    return coupon, coupon.discount_for(subtotal, delivery_charge), ""


@ensure_csrf_cookie
def cart(request):
    if request.method == "GET":
        checkout_token = secrets.token_urlsafe(24)
        request.session["checkout_token"] = checkout_token
        return render(request, "cart.html", {
            "pending_cart_item": request.session.pop("pending_cart_item", None),
            "emi_plans": EMIPlan.objects.filter(is_active=True),
            "addresses": get_or_create_customer(request.user).addresses.all() if request.user.is_authenticated else [],
            "checkout_token": checkout_token,
        })
    if not request.user.is_authenticated:
        return JsonResponse({
            "message": "Please login before checkout.",
            "login_url": f"{reverse('login')}?next={reverse('cart')}",
        }, status=401)
    customer = get_or_create_customer(request.user)
    try:
        data = json.loads(request.body)
        # Browser checkout carries a one-time token. Keep the JSON endpoint
        # backward compatible for existing clients that predate this field.
        if data.get("checkout_token") and data.get("checkout_token") != request.session.get("checkout_token"):
            return JsonResponse({"message": "This checkout has already been submitted. Refresh your bag to try again."}, status=409)
        raw_items = data.get("items", [])
        if not isinstance(raw_items, list) or not raw_items:
            raise ValueError
        quantities = defaultdict(int)
        for item in raw_items:
            product_id = int(item["product_id"])
            quantity = int(item["quantity"])
            if product_id < 1 or quantity < 1 or quantity > 10000:
                raise ValueError
            quantities[product_id] += quantity
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return JsonResponse({"message": "Your cart contains an invalid item."}, status=400)

    try:
        with transaction.atomic():
            # Lock products before checking stock so quantities never go negative.
            products = {
                product.pk: product
                for product in Product.objects.select_for_update().filter(pk__in=quantities)
            }
            if len(products) != len(quantities):
                raise Product.DoesNotExist
            for product_id, quantity in quantities.items():
                product = products[product_id]
                if not product.is_available or product.stock_quantity < quantity:
                    return JsonResponse({
                        "message": f"{product.name} no longer has enough stock. Please update your bag."
                    }, status=400)

            subtotal = sum((products[product_id].price * quantity for product_id, quantity in quantities.items()), Decimal("0.00"))
            delivery_charge = Decimal("0.00") if subtotal >= Decimal("499") else Decimal("49.00")
            coupon, coupon_discount, coupon_error = coupon_for_checkout(data.get("coupon_code", ""), request.user, subtotal, delivery_charge)
            if coupon_error:
                return JsonResponse({"message": coupon_error}, status=400)
            payment_method = data.get("payment_method", Order.PaymentMethod.COD)
            if payment_method not in Order.PaymentMethod.values:
                raise ValueError
            emi_plan = None
            if payment_method == Order.PaymentMethod.EMI:
                try:
                    emi_plan = EMIPlan.objects.select_for_update().get(pk=int(data.get("emi_plan_id")), is_active=True)
                except (EMIPlan.DoesNotExist, TypeError, ValueError):
                    return JsonResponse({"message": "Please select an available EMI plan."}, status=400)
                if not emi_plan.is_eligible_for(products.values(), subtotal + delivery_charge - coupon_discount):
                    return JsonResponse({"message": "The selected EMI plan is not eligible for this order."}, status=400)
            if payment_method == Order.PaymentMethod.ONLINE:
                return JsonResponse({"message": "Online payment is not configured. Set up a verified gateway before enabling this method."}, status=400)
            address = Address.objects.filter(customer=customer, pk=data.get("address_id")).first()
            if not address:
                return JsonResponse({"message": "Select a complete saved delivery address before placing your order."}, status=400)
            address_text = ", ".join(filter(None, [address.full_name, address.house, address.street, address.landmark]))
            city, state, pin = address.city, address.state, address.pin_code
            order = Order.objects.create(customer=customer, payment_successful=False, payment_method=payment_method, payment_status="PENDING", status=Order.Status.PLACED, coupon=coupon, subtotal_amount=subtotal, delivery_charge=delivery_charge, coupon_discount=coupon_discount, emi_plan=emi_plan, delivery_address_text=address_text, delivery_city=city, delivery_state=state, delivery_pin_code=pin)
            for product_id, quantity in quantities.items():
                product = products[product_id]
                was_low_stock = product.stock_quantity <= product.low_stock_threshold
                OrderItem.objects.create(order=order, product=product, quantity=quantity, price=product.price)
                product.stock_quantity -= quantity
                product.save(update_fields=["stock_quantity", "updated_at"])
                if not was_low_stock and product.stock_quantity <= product.low_stock_threshold:
                    Notification.objects.bulk_create([
                        Notification(
                            user=staff_user,
                            kind=Notification.Kind.INVENTORY,
                            title=f"Low stock: {product.name}",
                            message=f"Only {product.stock_quantity} item(s) remain for {product.name}.",
                            link="/admin/products/product/",
                        )
                        for staff_user in get_user_model().objects.filter(is_staff=True, is_active=True)
                    ])
            if coupon:
                CouponRedemption.objects.create(coupon=coupon, user=request.user, order=order)
                Coupon.objects.filter(pk=coupon.pk).update(times_used=F("times_used") + 1)
            order.add_status_history(Order.Status.PLACED, "Order placed by customer")
            order._create_notification("Order placed", f"Order #{order.pk} was placed successfully.")
            request.session.pop("checkout_token", None)
            transaction.on_commit(lambda: __import__("orders.services", fromlist=["export_order_after_commit"]).export_order_after_commit(order.pk))
    except Product.DoesNotExist:
        return JsonResponse({"message": "A product in your bag is no longer available."}, status=400)

    return JsonResponse({
        "success": True,
        "order_id": order.id,
        "redirect_url": reverse("order_detail", kwargs={"pk": order.id}) + "?placed=1",
        "total": str(order.total_amount),
    })


@login_required
def order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("customer", "customer__user").prefetch_related("items__product", "status_history"),
        pk=pk,
        customer__user=request.user,
    )
    timeline_statuses = [
        Order.Status.PLACED,
        Order.Status.CONFIRMED,
        Order.Status.PROCESSING,
        Order.Status.SHIPPED,
        Order.Status.OUT_FOR_DELIVERY,
        Order.Status.DELIVERED,
    ]
    completed_statuses = list(order.status_history.values_list("status", flat=True))
    return render(request, "orders/order_detail.html", {
        "order": order,
        "timeline_statuses": timeline_statuses,
        "completed_statuses": completed_statuses,
    })


@login_required
def order_list(request):
    orders = Order.objects.filter(customer__user=request.user).select_related("customer__user").prefetch_related("items")
    return render(request, "orders/order_list.html", {"orders": orders})


@login_required
@require_POST
def order_cancel(request, pk):
    with transaction.atomic():
        order = get_object_or_404(Order.objects.select_for_update(), pk=pk, customer__user=request.user)
        reason = request.POST.get("reason", "").strip()
        if not order.can_cancel:
            messages.error(request, "This order can no longer be cancelled.")
            return redirect("order_detail", pk=pk)
        if not reason:
            messages.error(request, "Please tell us why you are cancelling the order.")
            return redirect("order_detail", pk=pk)
        order.cancellation_reason = reason[:2000]
        order.save(update_fields=["cancellation_reason", "updated_at"])
        order.transition_to(Order.Status.CANCELLED, f"Customer cancellation: {reason[:400]}")
    messages.success(request, "Your order was cancelled. No online payment was captured.")
    return redirect("order_detail", pk=pk)


@login_required
@require_POST
def order_return_request(request, pk):
    with transaction.atomic():
        order = get_object_or_404(Order.objects.select_for_update(), pk=pk, customer__user=request.user)
        reason = request.POST.get("reason", "").strip()
        if not order.can_request_return:
            messages.error(request, "A return can only be requested after delivery.")
            return redirect("order_detail", pk=pk)
        if not reason:
            messages.error(request, "Please tell us why you would like to return the order.")
            return redirect("order_detail", pk=pk)
        order.return_reason = reason[:2000]
        order.save(update_fields=["return_reason", "updated_at"])
        order.transition_to(Order.Status.RETURN_REQUESTED, f"Customer return request: {reason[:400]}")
    messages.success(request, "Your return request has been submitted for review.")
    return redirect("order_detail", pk=pk)
