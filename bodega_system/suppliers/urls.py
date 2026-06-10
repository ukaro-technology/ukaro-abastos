# suppliers/urls.py

from django.urls import path
from . import views

app_name = 'suppliers'

urlpatterns = [
    path('', views.supplier_list, name='supplier_list'),
    path('add/', views.supplier_create, name='supplier_create'),
    path('<int:pk>/', views.supplier_detail, name='supplier_detail'),
    path('<int:pk>/edit/', views.supplier_update, name='supplier_update'),
    path('<int:pk>/delete/', views.supplier_delete, name='supplier_delete'),
    
    path('orders/', views.order_list, name='order_list'),
    path('orders/add/', views.order_create, name='order_create'),
    path('orders/<int:pk>/', views.order_detail, name='order_detail'),
    path('orders/<int:pk>/edit/', views.order_update, name='order_update'),
    path('orders/<int:pk>/receive/', views.order_receive, name='order_receive'),
    path('orders/<int:pk>/cancel/', views.order_cancel, name='order_cancel'),

    # Pagos a proveedores
    path('orders/<int:order_id>/payments/', views.payment_list, name='payment_list'),
    path('orders/<int:order_id>/payments/add/', views.payment_create, name='payment_create'),
    path('payments/<int:pk>/delete/', views.payment_delete, name='payment_delete'),

    # API endpoints
    path('api/product-lookup/<str:barcode>/', views.product_lookup_api, name='product_lookup_api'),
    path('orders/api/create/', views.order_create_api, name='order_create_api'),
]