from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Avg, Case, Count, FloatField, Q, Value, When
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render

from customers.models import WishlistItem
from orders.models import Order, OrderItem

from .forms import ProductForm, ReviewForm
from .models import Product, Review
from orders.models import EMIPlan


def with_ratings(queryset):
    return queryset.annotate(
        rating_average=Coalesce(Avg("reviews__rating"), Value(0.0), output_field=FloatField()),
        review_count=Count("reviews", distinct=True),
    )


def parse_decimal(value):
    if not value:
        return None
    try:
        value = Decimal(value)
    except (InvalidOperation, TypeError):
        return None
    return value if value >= 0 else None


def wishlist_ids_for(user):
    if not user.is_authenticated:
        return set()
    return set(WishlistItem.objects.filter(user=user).values_list("product_id", flat=True))


def index(request):
    q = request.GET.get("q", "").strip()
    selected_category = request.GET.get("category", "")
    selected_brand = request.GET.get("brand", "")
    availability = request.GET.get("availability", "")
    min_price = parse_decimal(request.GET.get("min_price", ""))
    max_price = parse_decimal(request.GET.get("max_price", ""))
    min_rating = request.GET.get("rating", "")
    sort = request.GET.get("sort", "relevance")
    errors = []

    products = Product.objects.all()
    if q:
        products = products.filter(
            Q(name__icontains=q)
            | Q(description__icontains=q)
            | Q(category__icontains=q)
            | Q(brand__icontains=q)
        )
    if selected_category in dict(Product.CATEGORY_CHOICES):
        products = products.filter(category=selected_category)
    if selected_brand:
        products = products.filter(brand=selected_brand)
    if request.GET.get("min_price") and min_price is None:
        errors.append("Minimum price must be a positive number.")
    if request.GET.get("max_price") and max_price is None:
        errors.append("Maximum price must be a positive number.")
    if min_price is not None:
        products = products.filter(price__gte=min_price)
    if max_price is not None:
        products = products.filter(price__lte=max_price)
    if min_price is not None and max_price is not None and min_price > max_price:
        errors.append("Minimum price cannot be greater than maximum price.")
        products = products.none()
    if availability == "in_stock":
        products = products.filter(is_available=True, stock_quantity__gt=0)
    elif availability == "out_of_stock":
        products = products.filter(Q(is_available=False) | Q(stock_quantity__lte=0))

    products = with_ratings(products)
    if min_rating:
        try:
            rating_value = int(min_rating)
            if rating_value not in range(1, 6):
                raise ValueError
            # Products without reviews remain discoverable; a rating filter only
            # excludes products with an established rating below the selection.
            products = products.filter(Q(rating_average__gte=rating_value) | Q(review_count=0))
        except ValueError:
            errors.append("Rating must be between 1 and 5.")
            min_rating = ""

    sort_options = {
        "price_low": "price",
        "price_high": "-price",
        "newest": "-created_at",
        "rating": "-rating_average",
    }
    if sort in sort_options:
        products = products.order_by(sort_options[sort], "-created_at")
    elif q:
        products = products.annotate(
            relevance=Case(
                When(name__icontains=q, then=Value(0)),
                When(brand__icontains=q, then=Value(1)),
                default=Value(2),
            )
        ).order_by("relevance", "-created_at")
    else:
        sort = "relevance"
        products = products.order_by("-created_at")

    product_count = products.count()
    paginator = Paginator(products, 12)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    filter_query = query_params.urlencode()
    brands = Product.objects.exclude(brand="").order_by("brand").values_list("brand", flat=True).distinct()
    featured_products = with_ratings(Product.objects.filter(is_available=True, stock_quantity__gt=0)).order_by("-created_at")[:4]
    category_sections = []
    if not any([q, selected_category, selected_brand, availability, request.GET.get("min_price"), request.GET.get("max_price")]):
        for code, label in Product.CATEGORY_CHOICES:
            section_products = with_ratings(Product.objects.filter(category=code, is_available=True, stock_quantity__gt=0)).order_by("-created_at")[:8]
            if section_products:
                category_sections.append({"code": code, "label": label, "products": section_products})

    return render(request, "index.html", {
        "products": page_obj.object_list,
        "page_obj": page_obj,
        "product_count": product_count,
        "categories": Product.CATEGORY_CHOICES,
        "brands": brands,
        "q": q,
        "selected_category": selected_category,
        "selected_brand": selected_brand,
        "availability": availability,
        "min_price": request.GET.get("min_price", ""),
        "max_price": request.GET.get("max_price", ""),
        "min_rating": min_rating,
        "sort": sort,
        "filter_errors": errors,
        "filter_query": filter_query,
        "featured_products": featured_products,
        "category_sections": category_sections,
        "wishlist_ids": wishlist_ids_for(request.user),
    })


def product_detail(request, pk):
    product = get_object_or_404(with_ratings(Product.objects.prefetch_related("images")), pk=pk)
    gallery_images = list(product.images.all())
    main_image_url = product.image.url if product.image else (gallery_images[0].image.url if gallery_images else "")
    review_sort = request.GET.get("review_sort", "recent")
    review_ordering = {"highest": "-rating", "lowest": "rating", "recent": "-created_at"}
    reviews = product.reviews.select_related("user").order_by(review_ordering.get(review_sort, "-created_at"))
    related_filter = Q(category=product.category) | Q(
        price__gte=product.price * Decimal("0.70"),
        price__lte=product.price * Decimal("1.30"),
    )
    if product.brand:
        related_filter |= Q(brand=product.brand)
    related_products = with_ratings(
        Product.objects.filter(related_filter, is_available=True, stock_quantity__gt=0).exclude(pk=product.pk)
    ).order_by("-rating_average", "-created_at")[:4]

    wishlist_ids = wishlist_ids_for(request.user)
    existing_review = None
    can_review = False
    if request.user.is_authenticated:
        existing_review = Review.objects.filter(product=product, user=request.user).first()
        can_review = OrderItem.objects.filter(
            product=product, order__customer__user=request.user
        ).exclude(order__status=Order.Status.CANCELLED).exists()

    return render(request, "products/product_detail.html", {
        "product": product,
        "reviews": reviews,
        "review_sort": review_sort,
        "review_form": ReviewForm(instance=existing_review),
        "existing_review": existing_review,
        "can_review": can_review,
        "is_wishlisted": product.pk in wishlist_ids,
        "wishlist_ids": wishlist_ids,
        "related_products": related_products,
        "gallery_images": gallery_images,
        "main_image_url": main_image_url,
        "emi_plans": [
            {"plan": plan, "monthly_amount": plan.installment(product.price)}
            for plan in EMIPlan.objects.filter(is_active=True)
            if plan.is_eligible_for([product], product.price)
        ],
    })


@login_required
def review_create(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if not OrderItem.objects.filter(product=product, order__customer__user=request.user).exclude(
        order__status=Order.Status.CANCELLED
    ).exists():
        messages.error(request, "Only customers who purchased this product can leave a review.")
        return redirect("product_detail", pk=product.pk)
    if Review.objects.filter(product=product, user=request.user).exists():
        messages.info(request, "You already reviewed this product. You can edit your review below.")
        return redirect("product_detail", pk=product.pk)
    if request.method != "POST":
        return redirect("product_detail", pk=product.pk)
    form = ReviewForm(request.POST)
    if form.is_valid():
        review = form.save(commit=False)
        review.product = product
        review.user = request.user
        review.verified_purchase = True
        review.save()
        messages.success(request, "Thanks for your verified-purchase review.")
    else:
        messages.error(request, "Please correct the review form and try again.")
    return redirect("product_detail", pk=product.pk)


@login_required
def review_edit(request, pk):
    review = get_object_or_404(Review, pk=pk, user=request.user)
    if request.method == "POST":
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            form.save()
            messages.success(request, "Your review was updated.")
        else:
            messages.error(request, "Please correct the review form and try again.")
    return redirect("product_detail", pk=review.product_id)


@login_required
def review_delete(request, pk):
    review = get_object_or_404(Review, pk=pk, user=request.user)
    product_id = review.product_id
    if request.method == "POST":
        review.delete()
        messages.success(request, "Your review was removed.")
    return redirect("product_detail", pk=product_id)


staff_required = user_passes_test(lambda user: user.is_staff)


@staff_required
def product_list(request):
    return render(request, "products/product_list.html", {"products": with_ratings(Product.objects.all())})


@staff_required
def product_create(request):
    form = ProductForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Product created.")
        return redirect("product_list")
    return render(request, "products/product_form.html", {"form": form})


@staff_required
def product_update(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Product updated.")
        return redirect("product_list")
    return render(request, "products/product_form.html", {"form": form, "product": product})


@staff_required
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        product.delete()
        messages.success(request, "Product removed.")
        return redirect("product_list")
    return render(request, "products/product_confirm_delete.html", {"product": product})
