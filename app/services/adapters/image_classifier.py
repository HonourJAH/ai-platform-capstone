import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from sqlmodel import Session

from app.celery_app import celery_app
from app.database import engine
from app.models import AsyncJob
from app.services.adapters.base import BaseAdapter


@celery_app.task(bind=True, name="classify_image")
def classify_image_task(self, job_id: str, image_url: str) -> None:
    with Session(engine) as session:
        job = session.get(AsyncJob, job_id)
        if job is None:
            return
        job.status = "processing"
        session.add(job)
        session.commit()

        try:
            # INTEGRATION POINT: replace with your Project 2 ResNet50 inference
            result = {
                "label": "placeholder_class",
                "confidence": 0.0,
                "image_url": image_url,
            }

            job.status = "done"
            job.result = json.dumps(result)
            job.completed_at = datetime.now(timezone.utc)
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.completed_at = datetime.now(timezone.utc)

        session.add(job)
        session.commit()


class ImageClassificationAdapter(BaseAdapter):
    task_type = "image_classification"
    is_async = True

    def enqueue(self, payload: Dict[str, Any]) -> str:
        job_id = str(uuid.uuid4())
        classify_image_task.apply_async(
            kwargs={"job_id": job_id, "image_url": payload["image_url"]},
            task_id=job_id,
        )
        return job_id
