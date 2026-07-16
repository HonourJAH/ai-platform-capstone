from abc import ABC
from typing import Any, Dict


class BaseAdapter(ABC):
    """Common interface every model adapter implements. The router only ever
    talks to this interface - it never knows whether a given task_type is
    scikit-learn, PyTorch, or a call out to Ollama."""

    task_type: str
    is_async: bool = False

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Run inference synchronously and return a JSON-serializable result.
        Only called for adapters where is_async is False."""
        raise NotImplementedError

    def enqueue(self, payload: Dict[str, Any]) -> str:
        """Queue a background job and return a Celery task id. Only called
        for adapters where is_async is True."""
        raise NotImplementedError
