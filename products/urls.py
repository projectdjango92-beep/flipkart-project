from django.urls import path

from . import views


urlpatterns = [

    path("smart-assistant/", views.smart_assistant, name="smart_assistant"),

    path(
        "",
        views.product_list,
        name="product_list",
    ),

    path(
        "create/",
        views.product_create,
        name="product_create",
    ),

    path(
        "update/<int:pk>/",
        views.product_update,
        name="product_update",
    ),

    path(
        "detail/<int:pk>/",
        views.product_detail,
        name="product_detail",
        ),

    path(
        "delete/<int:pk>/",
        views.product_delete,
        name="product_delete",
    ),
    path("detail/<int:pk>/reviews/add/", views.review_create, name="review_create"),
    path("reviews/<int:pk>/edit/", views.review_edit, name="review_edit"),
    path("reviews/<int:pk>/delete/", views.review_delete, name="review_delete"),
]
