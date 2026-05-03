from __future__ import annotations

import importlib
import os
from contextlib import nullcontext
from typing import Any, Optional

from inventory.domain.request_context import get_request_id
from inventory.ports.logger import ProductLogger


class LangSmithTracer:

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str,
        default_project: str,
        enabled: bool,
        logger: Optional[ProductLogger] = None,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._endpoint = (endpoint or "https://api.smith.langchain.com").strip()
        self._default_project = (default_project or "default").strip()
        self._enabled = bool(enabled and self._api_key)
        self._logger = logger
        self._trace_fn = None

        if self._enabled:
            self._configure_environment()
            self._load_trace_helper()

    def is_enabled(self) -> bool:
        return bool(self._enabled and self._trace_fn is not None)

    def trace(
        self,
        name: str,
        *,
        project_name: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        inputs: Optional[dict[str, Any]] = None,
    ):
        if not self.is_enabled():
            return nullcontext()
        trace_fn = self._trace_fn
        if trace_fn is None:
            return nullcontext()

        payload_metadata = dict(metadata or {})
        payload_metadata.setdefault("request_id", get_request_id())

        payload_inputs = dict(inputs or {})
        effective_project = (project_name or self._default_project).strip() or self._default_project

        try:
            return trace_fn(
                name=name,
                project_name=effective_project,
                metadata=payload_metadata,
                inputs=payload_inputs,
            )
        except TypeError:
            try:
                return trace_fn(
                    name=name,
                    project=effective_project,
                    metadata=payload_metadata,
                    inputs=payload_inputs,
                )
            except Exception as e:
                self._warn("LangSmith trace invocation failed", error=str(e), trace_name=name)
                return nullcontext()
        except Exception as e:
            self._warn("LangSmith trace invocation failed", error=str(e), trace_name=name)
            return nullcontext()

    def _configure_environment(self) -> None:
        os.environ["LANGSMITH_API_KEY"] = self._api_key
        os.environ["LANGSMITH_ENDPOINT"] = self._endpoint
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ.setdefault("LANGSMITH_PROJECT", self._default_project)

    def _load_trace_helper(self) -> None:
        try:
            run_helpers = importlib.import_module("langsmith.run_helpers")
            self._trace_fn = getattr(run_helpers, "trace", None)
            if self._trace_fn is None:
                self._enabled = False
                self._warn("LangSmith trace helper not found; tracing disabled")
        except Exception as e:
            self._enabled = False
            self._warn("LangSmith import failed; tracing disabled", error=str(e))

    def _warn(self, message: str, **context: Any) -> None:
        if self._logger:
            self._logger.warning(message, **context)
