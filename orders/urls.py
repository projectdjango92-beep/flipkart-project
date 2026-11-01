from django.urls import path

from . import views


urlpatterns = [
    path("export/download/", views.download_order_export, name="download_order_export"),
    path("payment/upi/<int:pk>/", views.upi_payment, name="upi_payment"),
    path(
        "cart/",
        views.cart,
        name="cart",
    ),

    path(
        "",
        views.order_list,
        name="order_list",
    ),

    path(
        "detail/<int:pk>/",
        views.order_detail,
        name="order_detail",
        ),
    path("detail/<int:pk>/cancel/", views.order_cancel, name="order_cancel"),
    path("detail/<int:pk>/return/", views.order_return_request, name="order_return_request"),
]
