import uuid
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar('request_id', default='no-request-id')

def set_request_id(request_id: str) -> None:
    request_id_var.set(request_id)

def set_new_request_id() -> str:
    request_id = str(uuid.uuid4())
    request_id_var.set(request_id)
    return request_id

def get_request_id() -> str:
    return request_id_var.get()
