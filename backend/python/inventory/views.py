from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from inventory.domain.exceptions import ValidationError, NotFoundError, DuplicateError
from inventory.adapters.in_memory_repository import product_repository
from inventory.services.product_service import ProductService

service = ProductService(product_repository)

# POST /api/products/
@api_view(['POST'])
def create_product(request):
    try:
        product = service.create_product(request.data)
        return Response(product, status=status.HTTP_201_CREATED)
    except ValidationError as e:
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except DuplicateError as e:
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)

# GET /api/products/detail/?id=<product_id>
@api_view(['GET'])
def get_product(request):
    try:
        product = service.get_product(request.query_params.get('id'))
        return Response(product)
    except ValidationError as e:
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except NotFoundError as e:
        return Response({'error': e.message}, status=status.HTTP_404_NOT_FOUND)

# GET /api/products/
@api_view(['GET'])
def list_products(request):
    try:
        result = service.list_products(
            category=request.query_params.get('category'),
            search=request.query_params.get('search'),
            raw_page=request.query_params.get('page'),
            raw_page_size=request.query_params.get('page_size'),
        )
        return Response(result)
    except ValidationError as e:
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)

# PUT/PATCH /api/products/update/?id=<product_id>
@api_view(['PUT', 'PATCH'])
def update_product(request):
    try:
        product = service.update_product(
            request.query_params.get('id'),
            request.data,
        )
        return Response(product)
    except ValidationError as e:
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except NotFoundError as e:
        return Response({'error': e.message}, status=status.HTTP_404_NOT_FOUND)
    except DuplicateError as e:
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)

# DELETE /api/products/delete/?id=<product_id>
@api_view(['DELETE'])
def delete_product(request):
    try:
        service.delete_product(request.query_params.get('id'))
        return Response(
            {'message': 'Product deleted successfully'},
            status=status.HTTP_204_NO_CONTENT,
        )
    except ValidationError as e:
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except NotFoundError as e:
        return Response({'error': e.message}, status=status.HTTP_404_NOT_FOUND)