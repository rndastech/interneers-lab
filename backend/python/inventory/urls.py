from django.urls import path
from .views import (
    products_list_create,
    product_detail_update_delete,
)

urlpatterns = [
    path('products/', products_list_create, name='product-list-create'),
    path('products/<str:product_id>/', product_detail_update_delete, name='product-detail'),
]
