import logging
from typing import Any, Dict

import httpx

from app.config import settings
from app.services.adapters.base import BaseAdapter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _warm_up_model() -> None:
    try:
        response = httpx.post(
            settings.ollama_url,
            json={"model": settings.ollama_model, "prompt": "hi", "stream": False},
            timeout=300.0,
        )
        logger.info(
            "Ollama warmup: status=%s body=%s",
            response.status_code,
            response.text[:300],
        )
    except Exception as exc:
        logger.warning("Could not warm up Ollama model at startup: %s", exc)


_warm_up_model()


class LLMChatAdapter(BaseAdapter):
    task_type = "llm_chat"
    is_async = False

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        message = payload["message"]

        response = httpx.post(
            settings.ollama_url,
            json={"model": settings.ollama_model, "prompt": message, "stream": False},
            timeout=300.0,
        )

        if response.status_code != 200:
            logger.error(
                "Ollama returned non-200: status=%s body=%s request_json=%s",
                response.status_code,
                response.text[:500],
                {
                    "model": settings.ollama_model,
                    "prompt": message[:100],
                    "stream": False,
                },
            )

        response.raise_for_status()
        reply = response.json().get("response", "")

        return {"reply": reply}
