from django.urls import path
from .views import (
    create_product,
    get_product,
    list_products,
    update_product,
    delete_product
)

urlpatterns = [
    path('products/', list_products, name='product-list'),
    path('products/create/', create_product, name='product-create'),
    path('products/detail/', get_product, name='product-detail'),
    path('products/update/', update_product, name='product-update'),
    path('products/delete/', delete_product, name='product-delete'),
]
