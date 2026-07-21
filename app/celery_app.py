from celery import Celery

from app.config import settings

celery_app = Celery(
    "ai_platform",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.services.adapters.image_classifier"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
)
