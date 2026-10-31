from django.urls import path

from . import views


urlpatterns = [

    path(
        "register/",
        views.register,
        name="register",
    ),
    path("wishlist/", views.wishlist, name="wishlist"),
    path("wishlist/toggle/<int:pk>/", views.wishlist_toggle, name="wishlist_toggle"),
    path("wishlist/remove/<int:pk>/", views.wishlist_remove, name="wishlist_remove"),
    path("wishlist/move-to-cart/<int:pk>/", views.wishlist_move_to_cart, name="wishlist_move_to_cart"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/<int:pk>/read/", views.notification_read, name="notification_read"),
    path("notifications/read-all/", views.notifications_mark_all_read, name="notifications_mark_all_read"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.account_profile, name="account_profile"),
    path("profile/save/", views.profile_update, name="profile_update"),
    path("orders/", views.account_orders, name="account_orders"),
    path("wishlist/account/", views.account_wishlist, name="account_wishlist"),
    path("addresses/", views.account_addresses, name="account_addresses"),
    path("delivery-location/", views.account_location, name="account_location"),
    path("coupons/", views.account_coupons, name="account_coupons"),
    path("settings/", views.account_settings, name="account_settings"),
    path("addresses/add/", views.address_save, name="address_add"),
    path("addresses/<int:pk>/", views.address_save, name="address_update"),
    path("addresses/<int:pk>/delete/", views.address_delete, name="address_delete"),
]
