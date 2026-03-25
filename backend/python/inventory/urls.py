from django.urls import path
from .views import (
    products_list_create,
    product_detail_update_delete,
    products_csv,
    categories_list_create,
    category_detail_update_delete,
    ai_text,
    ai_product,
    ai_scenarios,
)

urlpatterns = [
    path('products/', products_list_create, name='product-list-create'),
    path('products/csv/', products_csv, name='product-csv'),
    path('products/<str:product_id>/', product_detail_update_delete, name='product-detail'),
    path('categories/', categories_list_create, name='category-list-create'),
    path('categories/<str:category_id>/', category_detail_update_delete, name='category-detail'),
    path('ai/prompt/', ai_text, name='text-generate'),
    path('ai/product/', ai_product, name='product-generate'),
    path('ai/scenarios/', ai_scenarios, name='scenario-generate'),
]
