from inventory.domain.request_context import set_request_id, set_new_request_id

class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming_id = request.headers.get('X-Request-ID')
        if incoming_id:
            set_request_id(incoming_id)
            request_id = incoming_id
        else:
            request_id = set_new_request_id()

        request.request_id = request_id
        response = self.get_response(request)
        response['X-Request-ID'] = request_id
        return response
