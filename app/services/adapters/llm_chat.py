from typing import Any, Dict

import httpx

from app.services.adapters.base import BaseAdapter

OLLAMA_URL = "http://host.docker.internal:11434/api/generate"


class LLMChatAdapter(BaseAdapter):
    task_type = "llm_chat"
    is_async = False

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        message = payload["message"]

        response = httpx.post(
            OLLAMA_URL,
            json={"model": "llama3", "prompt": message, "stream": False},
            timeout=30.0,
        )
        response.raise_for_status()
        reply = response.json().get("response", "")

        return {"reply": reply}
