from typing import Any, Dict

import httpx

from app.services.adapters.base import BaseAdapter

OLLAMA_URL = "http://host.docker.internal:11434/api/generate"


class RAGAdapter(BaseAdapter):
    task_type = "rag_query"
    is_async = False

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        query = payload["query"]

        retrieved_chunks = [f"[retrieved context for: {query}]"]
        prompt = f"Context:\n{retrieved_chunks}\n\nQuestion: {query}\nAnswer:"

        response = httpx.post(
            OLLAMA_URL,
            json={"model": "llama3", "prompt": prompt, "stream": False},
            timeout=30.0,
        )
        response.raise_for_status()
        answer = response.json().get("response", "")

        return {"answer": answer, "sources": retrieved_chunks}
