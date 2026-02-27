from __future__ import annotations
import logging
from typing import Any
from inventory.domain.request_context import get_request_id
from inventory.ports.logger import ProductLogger

class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(record, "request_id", None) or get_request_id()
        record.service = {"name": "inventory-api"}
        return True


class PythonProductLogger(ProductLogger):
    __slots__ = ("_logger",)

    def __init__(self, name: str = "inventory") -> None:
        self._logger: logging.Logger = logging.getLogger(name)

    def _log(self, level: int, message: str, **context: Any) -> None:
        if not self._logger.isEnabledFor(level):
            return
        log_kwargs = {
            k: context.pop(k)
            for k in ("exc_info", "stack_info", "stacklevel")
            if k in context
        }
        self._logger.log(level, message, extra=context, **log_kwargs)

    def debug(self, message: str, **context: Any) -> None:
        self._log(logging.DEBUG, message, **context)

    def info(self, message: str, **context: Any) -> None:
        self._log(logging.INFO, message, **context)

    def warning(self, message: str, **context: Any) -> None:
        self._log(logging.WARNING, message, **context)

    def error(self, message: str, **context: Any) -> None:
        self._log(logging.ERROR, message, **context)

    def critical(self, message: str, **context: Any) -> None:
        self._log(logging.CRITICAL, message, **context)
