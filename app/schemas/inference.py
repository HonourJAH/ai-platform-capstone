from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class TextClassificationPayload(BaseModel):
    task_type: Literal["text_classification"]
    text: str


class ImageClassificationPayload(BaseModel):
    task_type: Literal["image_classification"]
    image_url: str


class RAGQueryPayload(BaseModel):
    task_type: Literal["rag_query"]
    query: str


class LLMChatPayload(BaseModel):
    task_type: Literal["llm_chat"]
    message: str


InferenceRequest = Annotated[
    Union[
        TextClassificationPayload,
        ImageClassificationPayload,
        RAGQueryPayload,
        LLMChatPayload,
    ],
    Field(discriminator="task_type"),
]


class InferenceResponse(BaseModel):
    task_type: str
    status: Literal["completed", "queued"]
    result: dict | None = None
    job_id: str | None = None
