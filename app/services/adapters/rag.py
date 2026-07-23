import logging
from typing import Any, Dict

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from qdrant_client.http.exceptions import UnexpectedResponse
from sentence_transformers import SentenceTransformer

from app.config import settings
from app.services.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)

_embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
_qdrant_client = QdrantClient(
    host=settings.qdrant_host, port=settings.qdrant_port, timeout=30
)

_VECTOR_SIZE = 384


def _ensure_collection() -> None:
    """Best-effort at import time: a transient Qdrant hiccup here must not
    crash the whole adapters package and take every other adapter down with
    it. If this fails, rag_query will fail at request time instead - a much
    smaller blast radius than an unrelated adapter (e.g. image classification)
    never getting registered at all."""
    try:
        existing = [c.name for c in _qdrant_client.get_collections().collections]
        if settings.rag_collection_name not in existing:
            _qdrant_client.create_collection(
                collection_name=settings.rag_collection_name,
                vectors_config=VectorParams(
                    size=_VECTOR_SIZE, distance=Distance.COSINE
                ),
            )
    except UnexpectedResponse as exc:
        if exc.status_code != 409:
            logger.warning(
                "Could not verify/create Qdrant collection at startup: %s", exc
            )
    except Exception as exc:
        logger.warning("Could not verify/create Qdrant collection at startup: %s", exc)


_ensure_collection()


def _build_prompt(question: str, context_chunks: list[str]) -> str:
    context = "\n\n".join(
        f"[Chunk {i + 1}]:\n{chunk}" for i, chunk in enumerate(context_chunks)
    )
    return f"""You are a helpful assistant. Answer the question below using only the provided context.
If the answer cannot be found in the context, say "I don't have enough information to answer that."

Context:
{context}

Question: {question}

Answer:"""


class RAGAdapter(BaseAdapter):
    task_type = "rag_query"
    is_async = False

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        query = payload["query"]

        query_vector = _embedding_model.encode(query).tolist()

        results = _qdrant_client.query_points(
            collection_name=settings.rag_collection_name,
            query=query_vector,
            limit=5,
        )
        chunks = [point.payload["chunk_text"] for point in results.points]
        sources = [point.payload["document_name"] for point in results.points]

        prompt = _build_prompt(query, chunks)

        response = httpx.post(
            settings.ollama_url,
            json={"model": settings.ollama_model, "prompt": prompt, "stream": False},
            timeout=180.0,
        )
        response.raise_for_status()
        answer = response.json()["response"]

        return {"answer": answer, "sources": sources}
