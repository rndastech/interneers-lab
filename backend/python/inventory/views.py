from urllib.parse import urlencode

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from inventory.domain.exceptions import ValidationError, NotFoundError, DuplicateError
from inventory.adapters.product_repository import product_repository
from inventory.adapters.category_repository import category_repository
from inventory.adapters.python_logger import PythonProductLogger
from inventory.adapters.google_genai_provider import get_google_genai_provider
from inventory.services.product_service import ProductService
from inventory.services.category_service import CategoryService
from inventory.services.ai_service import AIService

logger = PythonProductLogger("inventory.views")
service = ProductService(product_repository, logger, category_repository)
category_service = CategoryService(category_repository, logger)
ai_service = AIService(get_google_genai_provider(), logger, product_repository, category_service, service)

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
    except NotFoundError as e:
        logger.error('HTTP 404 - referenced resource not found on create', error=e.message)
        return Response({'error': e.message}, status=status.HTTP_404_NOT_FOUND)
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
    categories = request.query_params.getlist('category') or None
    logger.info(
        'HTTP GET /products - list_products request received',
        categories=categories,
        search=request.query_params.get('search'),
        page_size=request.query_params.get('page_size'),
        after=request.query_params.get('after'),
    )
    try:
        result = service.list_products(
            categories=categories,
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


def bulk_creates(request):
    logger.info('HTTP POST /products/csv/ - bulk_creates request received')
    try:
        result = service.create_product_csv(request.FILES.get('file'))
        created_count = len(result['created'])
        error_count = len(result['errors'])
        http_status = status.HTTP_207_MULTI_STATUS if error_count > 0 else status.HTTP_201_CREATED
        logger.info(
            'HTTP 201/207 - bulk CSV create complete',
            created_count=created_count,
            error_count=error_count,
        )
        return Response(
            {
                'created_count': created_count,
                'error_count': error_count,
                'created': result['created'],
                'errors': result['errors'],
            },
            status=http_status,
        )
    except ValidationError as exc:
        logger.error('HTTP 400 - validation error on bulk CSV create', error=exc.message)
        return Response({'error': exc.message}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.critical('HTTP 500 - unexpected error on bulk CSV create', exc_info=True)
        return Response({'error': INTERNAL_SERVER_ERROR_MESSAGE}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def bulk_updates(request):
    logger.info('HTTP PUT/PATCH /products/csv/ - bulk_updates request received')
    try:
        result = service.update_product_csv(request.FILES.get('file'))
        updated_count = len(result['updated'])
        error_count = len(result['errors'])
        http_status = status.HTTP_207_MULTI_STATUS if error_count > 0 else status.HTTP_200_OK
        logger.info(
            'HTTP 200/207 - bulk CSV update complete',
            updated_count=updated_count,
            error_count=error_count,
        )
        return Response(
            {
                'updated_count': updated_count,
                'error_count': error_count,
                'updated': result['updated'],
                'errors': result['errors'],
            },
            status=http_status,
        )
    except ValidationError as exc:
        logger.error('HTTP 400 - validation error on bulk CSV update', error=exc.message)
        return Response({'error': exc.message}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.critical('HTTP 500 - unexpected error on bulk CSV update', exc_info=True)
        return Response({'error': INTERNAL_SERVER_ERROR_MESSAGE}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def bulk_deletes(request):
    logger.info('HTTP DELETE /products/csv/ - bulk_deletes request received')
    try:
        result = service.delete_product_csv(request.FILES.get('file'))
        deleted_count = len(result['deleted'])
        error_count = len(result['errors'])
        http_status = status.HTTP_207_MULTI_STATUS if error_count > 0 else status.HTTP_200_OK
        logger.info(
            'HTTP 200/207 - bulk CSV delete complete',
            deleted_count=deleted_count,
            error_count=error_count,
        )
        return Response(
            {
                'deleted_count': deleted_count,
                'error_count': error_count,
                'deleted': result['deleted'],
                'errors': result['errors'],
            },
            status=http_status,
        )
    except ValidationError as exc:
        logger.error('HTTP 400 - validation error on bulk CSV delete', error=exc.message)
        return Response({'error': exc.message}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.critical('HTTP 500 - unexpected error on bulk CSV delete', exc_info=True)
        return Response({'error': INTERNAL_SERVER_ERROR_MESSAGE}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# POST          /api/products/csv/  = bulk create from CSV
# PUT / PATCH   /api/products/csv/  = bulk update from CSV
# DELETE        /api/products/csv/  = bulk delete from CSV
@api_view(['POST', 'PUT', 'PATCH', 'DELETE'])
def products_csv(request):
    if request.method == 'POST':
        return bulk_creates(request)
    if request.method in ('PUT', 'PATCH'):
        return bulk_updates(request)
    return bulk_deletes(request)



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


def create_category(request):
    logger.info(
        'HTTP POST /categories - create_category request received',
        fields=list(request.data.keys()),
    )
    try:
        category = category_service.create_category(request.data)
        logger.info('HTTP 201 - category created', category_id=category['id'])
        return Response(category, status=status.HTTP_201_CREATED)
    except ValidationError as e:
        logger.error('HTTP 400 - validation error on create', error=e.message)
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except DuplicateError as e:
        logger.error('HTTP 400 - duplicate error on create', error=e.message)
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.critical('HTTP 500 - unexpected error on create', exc_info=True)
        return Response({'error': INTERNAL_SERVER_ERROR_MESSAGE}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def get_category(category_id):
    logger.info('HTTP GET /categories/<id> - get_category request received', category_id=category_id)
    try:
        category = category_service.get_category(category_id)
        logger.info('HTTP 200 - category retrieved', category_id=category_id)
        return Response(category)
    except ValidationError as e:
        logger.error('HTTP 400 - invalid category ID', category_id=category_id, error=e.message)
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except NotFoundError as e:
        logger.error('HTTP 404 - category not found', category_id=category_id, error=e.message)
        return Response({'error': e.message}, status=status.HTTP_404_NOT_FOUND)
    except Exception:
        logger.critical('HTTP 500 - unexpected error on get', category_id=category_id, exc_info=True)
        return Response({'error': INTERNAL_SERVER_ERROR_MESSAGE}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def list_categories(request):
    logger.info(
        'HTTP GET /categories - list_categories request received',
        search=request.query_params.get('search'),
        page_size=request.query_params.get('page_size'),
        after=request.query_params.get('after'),
    )
    try:
        result = category_service.list_categories(
            raw_page_size=request.query_params.get('page_size'),
            raw_after=request.query_params.get('after'),
            search=request.query_params.get('search'),
        )
        next_cursor = result.pop('next_cursor')
        if next_cursor is not None:
            params = request.query_params.copy()
            params['after'] = next_cursor
            next_url = request.build_absolute_uri('?' + urlencode(params))
        else:
            next_url = None
        result = {
            'count': len(result['results']),
            'page_size': result['page_size'],
            'next': next_url,
            'results': result['results'],
        }
        logger.info('HTTP 200 - category list returned', returned_count=len(result['results']))
        return Response(result)
    except ValidationError as e:
        logger.error('HTTP 400 - validation error on list', error=e.message)
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.critical('HTTP 500 - unexpected error on list', exc_info=True)
        return Response({'error': INTERNAL_SERVER_ERROR_MESSAGE}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def update_category(request, category_id):
    logger.info(
        'HTTP PUT/PATCH /categories/<id> - update_category request received',
        category_id=category_id,
        fields=list(request.data.keys()),
    )
    try:
        category = category_service.update_category(category_id, request.data)
        logger.info('HTTP 200 - category updated', category_id=category_id)
        return Response(category)
    except ValidationError as e:
        logger.error('HTTP 400 - validation error on update', category_id=category_id, error=e.message)
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except NotFoundError as e:
        logger.error('HTTP 404 - category not found on update', category_id=category_id, error=e.message)
        return Response({'error': e.message}, status=status.HTTP_404_NOT_FOUND)
    except DuplicateError as e:
        logger.error('HTTP 400 - duplicate error on update', category_id=category_id, error=e.message)
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.critical('HTTP 500 - unexpected error on update', category_id=category_id, exc_info=True)
        return Response({'error': INTERNAL_SERVER_ERROR_MESSAGE}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def delete_category(category_id):
    logger.info('HTTP DELETE /categories/<id> - delete_category request received', category_id=category_id)
    try:
        category_service.delete_category(category_id)
        logger.info('HTTP 204 - category deleted', category_id=category_id)
        return Response(
            {'message': 'Category deleted successfully'},
            status=status.HTTP_204_NO_CONTENT,
        )
    except ValidationError as e:
        logger.error('HTTP 400 - invalid category ID on delete', category_id=category_id, error=e.message)
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except NotFoundError as e:
        logger.error('HTTP 404 - category not found on delete', category_id=category_id, error=e.message)
        return Response({'error': e.message}, status=status.HTTP_404_NOT_FOUND)
    except Exception:
        logger.critical('HTTP 500 - unexpected error on delete', category_id=category_id, exc_info=True)
        return Response({'error': INTERNAL_SERVER_ERROR_MESSAGE}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# POST /api/categories/   = create
# GET  /api/categories/   = list
@api_view(['GET', 'POST'])
def categories_list_create(request):
    if request.method == 'POST':
        return create_category(request)
    return list_categories(request)


# GET    /api/categories/{category_id}/  = retrieve
# PUT    /api/categories/{category_id}/  = full update
# PATCH  /api/categories/{category_id}/  = partial update
# DELETE /api/categories/{category_id}/  = delete
@api_view(['GET', 'PUT', 'PATCH', 'DELETE'])
def category_detail_update_delete(request, category_id):
    if request.method == 'GET':
        return get_category(category_id)
    if request.method in ('PUT', 'PATCH'):
        return update_category(request, category_id)
    return delete_category(category_id)

def text_generate(request):
    logger.info('HTTP POST /ai/ - text_generate received')
    try:
        response = ai_service.generate_text(request.data)
        logger.info('HTTP 200 - AI request processed successfully')
        return Response(response)
    except ValidationError as e:
        logger.error('HTTP 400 - validation error on AI request', error=e.message)
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.critical('HTTP 500 - unexpected error on AI request', exc_info=True)
        return Response({'error': INTERNAL_SERVER_ERROR_MESSAGE}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def product_generate(request):
    logger.info('HTTP POST /ai/product/ - product_generate received')
    try:
        response = ai_service.generate_products(request.data)
        logger.info('HTTP 200 - AI product request processed successfully')
        return Response(response)
    except ValidationError as e:
        logger.error('HTTP 400 - validation error on AI product request', error=e.message)
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.critical('HTTP 500 - unexpected error on AI product request', exc_info=True)
        return Response({'error': INTERNAL_SERVER_ERROR_MESSAGE}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
def scenario_products(request):
    logger.info('HTTP POST /ai/scenarios/ - ai_scenarios received', scenario=request.data.get('scenario'))
    try:
        response = ai_service.generate_scenario_products(request.data)
        logger.info('HTTP 201 - AI scenario request processed successfully', scenario=request.data.get('scenario'))
        return Response(response, status=status.HTTP_201_CREATED)
    except ValidationError as e:
        logger.error('HTTP 400 - validation error on AI scenario request', error=e.message)
        return Response({'error': e.message}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.critical('HTTP 500 - unexpected error on AI scenario request', exc_info=True)
        return Response({'error': INTERNAL_SERVER_ERROR_MESSAGE}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(['GET'])
def ai_text(request):
    return text_generate(request)

@api_view(['POST'])
def ai_product(request):
    return product_generate(request)

@api_view(['POST'])
def ai_scenarios(request):
    return scenario_products(request)
