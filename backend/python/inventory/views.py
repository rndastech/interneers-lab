from urllib.parse import urlencode

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from inventory.domain.exceptions import ValidationError, NotFoundError, DuplicateError
from inventory.adapters.mongo_repository import product_repository
from inventory.adapters.python_logger import PythonProductLogger
from inventory.services.product_service import ProductService

logger = PythonProductLogger("inventory.views")
service = ProductService(product_repository, logger)

INTERNAL_SERVER_ERROR_MESSAGE = 'An unexpected internal error occurred'

def create_product(request):
    logger.info(
        'HTTP POST /products - create_product request received',
        fields=list(request.data.keys()),
    )
    try:
        product = service.create_product(request.data)
        logger.info('HTTP 201 - product created', product_id=product['id'])
        return Response(product, status=status.HTTP_201_CREATED)
    except ValidationError as e:
        logger.error('HTTP 400 - validation error on create', error=e.message)
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except DuplicateError as e:
        logger.error('HTTP 400 - duplicate error on create', error=e.message)
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.critical('HTTP 500 - unexpected error on create', exc_info=True)
        return Response({'error': INTERNAL_SERVER_ERROR_MESSAGE}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def get_product(product_id):
    logger.info('HTTP GET /products/<id> - get_product request received', product_id=product_id)
    try:
        product = service.get_product(product_id)
        logger.info('HTTP 200 - product retrieved', product_id=product_id)
        return Response(product)
    except ValidationError as e:
        logger.error('HTTP 400 - invalid product ID', product_id=product_id, error=e.message)
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except NotFoundError as e:
        logger.error('HTTP 404 - product not found', product_id=product_id, error=e.message)
        return Response({'error': e.message}, status=status.HTTP_404_NOT_FOUND)
    except Exception:
        logger.critical('HTTP 500 - unexpected error on get', product_id=product_id, exc_info=True)
        return Response({'error': INTERNAL_SERVER_ERROR_MESSAGE}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def list_products(request):
    logger.info(
        'HTTP GET /products - list_products request received',
        category=request.query_params.get('category'),
        search=request.query_params.get('search'),
        page_size=request.query_params.get('page_size'),
        after=request.query_params.get('after'),
    )
    try:
        result = service.list_products(
            category=request.query_params.get('category'),
            search=request.query_params.get('search'),
            raw_page_size=request.query_params.get('page_size'),
            raw_after=request.query_params.get('after'),
        )
        next_cursor = result.pop('next_cursor')
        if next_cursor is not None:
            params = request.query_params.copy()
            params['after'] = next_cursor
            next_url = request.build_absolute_uri(
                '?' + urlencode(params)
            )
        else:
            next_url = None
        result = {
            'count': len(result['results']),
            'page_size': result['page_size'],
            'next': next_url,
            'results': result['results'],
        }
        logger.info('HTTP 200 - product list returned', returned_count=len(result['results']))
        return Response(result)
    except ValidationError as e:
        logger.error('HTTP 400 - validation error on list', error=e.message)
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.critical('HTTP 500 - unexpected error on list', exc_info=True)
        return Response({'error': INTERNAL_SERVER_ERROR_MESSAGE}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def update_product(request, product_id):
    logger.info(
        'HTTP PUT/PATCH /products/<id> - update_product request received',
        product_id=product_id,
        fields=list(request.data.keys()),
    )
    try:
        product = service.update_product(product_id, request.data)
        logger.info('HTTP 200 - product updated', product_id=product_id)
        return Response(product)
    except ValidationError as e:
        logger.error('HTTP 400 - validation error on update', product_id=product_id, error=e.message)
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except NotFoundError as e:
        logger.error('HTTP 404 - product not found on update', product_id=product_id, error=e.message)
        return Response({'error': e.message}, status=status.HTTP_404_NOT_FOUND)
    except DuplicateError as e:
        logger.error('HTTP 400 - duplicate error on update', product_id=product_id, error=e.message)
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.critical('HTTP 500 - unexpected error on update', product_id=product_id, exc_info=True)
        return Response({'error': INTERNAL_SERVER_ERROR_MESSAGE}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def delete_product(product_id):
    logger.info('HTTP DELETE /products/<id> - delete_product request received', product_id=product_id)
    try:
        service.delete_product(product_id)
        logger.info('HTTP 204 - product deleted', product_id=product_id)
        return Response(
            {'message': 'Product deleted successfully'},
            status=status.HTTP_204_NO_CONTENT,
        )
    except ValidationError as e:
        logger.error('HTTP 400 - invalid product ID on delete', product_id=product_id, error=e.message)
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except NotFoundError as e:
        logger.error('HTTP 404 - product not found on delete', product_id=product_id, error=e.message)
        return Response({'error': e.message}, status=status.HTTP_404_NOT_FOUND)
    except Exception:
        logger.critical('HTTP 500 - unexpected error on delete', product_id=product_id, exc_info=True)
        return Response({'error': INTERNAL_SERVER_ERROR_MESSAGE}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# POST /api/products/   = create
# GET  /api/products/   = list
@api_view(['GET', 'POST'])
def products_list_create(request):
    if request.method == 'POST':
        return create_product(request)
    return list_products(request)


# GET    /api/products/{product_id}/  = retrieve
# PUT    /api/products/{product_id}/  = full update
# PATCH  /api/products/{product_id}/  = partial update
# DELETE /api/products/{product_id}/  = delete
@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
def product_detail_update_delete(request, product_id):
    if request.method == 'GET':
        return get_product(product_id)
    if request.method in ('PUT', 'PATCH'):
        return update_product(request, product_id)
    return delete_product(product_id)
