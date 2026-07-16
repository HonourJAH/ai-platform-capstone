from app.services.adapters.base import BaseAdapter
from app.services.adapters.image_classifier import ImageClassificationAdapter
from app.services.adapters.llm_chat import LLMChatAdapter
from app.services.adapters.rag import RAGAdapter
from app.services.adapters.text_classifier import TextClassificationAdapter

ADAPTER_REGISTRY: dict[str, BaseAdapter] = {
    "text_classification": TextClassificationAdapter(),
    "rag_query": RAGAdapter(),
    "llm_chat": LLMChatAdapter(),
    "image_classification": ImageClassificationAdapter(),
}


def get_adapter(task_type: str) -> BaseAdapter:
    adapter = ADAPTER_REGISTRY.get(task_type)
    if adapter is None:
        raise KeyError(f"Unknown task_type: {task_type}")
    return adapter
