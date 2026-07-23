import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import httpx
import torch
from PIL import Image
from sqlmodel import Session
from torchvision.models import resnet50, ResNet50_Weights

from app.celery_app import celery_app
from app.database import engine
from app.models import AsyncJob
from app.services.adapters.base import BaseAdapter

logger = logging.getLogger(__name__)

_weights = ResNet50_Weights.DEFAULT
_model = resnet50(weights=_weights)
_model.eval()
_categories = _weights.meta["categories"]
_preprocess = _weights.transforms()


@celery_app.task(bind=True, name="classify_image")
def classify_image_task(self, job_id: str, image_url: str) -> None:
    logger.info("classify_image_task starting for job_id=%s", job_id)

    with Session(engine) as session:
        job = session.get(AsyncJob, job_id)
        if job is None:
            logger.warning(
                "classify_image_task: no AsyncJob row found for job_id=%s - "
                "this task will no-op. This means the row was never committed "
                "before the task started, or the job_id passed to Celery does "
                "not match the job_id stored in the database.",
                job_id,
            )
            return

        job.status = "processing"
        session.add(job)
        session.commit()

        try:
            response = httpx.get(
                image_url,
                timeout=15.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; AIInferencePlatform/1.0)"
                },
            )
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content)).convert("RGB")

            tensor = _preprocess(image).unsqueeze(0)

            with torch.no_grad():
                output = _model(tensor)
                probs = torch.softmax(output, dim=1)

            class_idx = probs.argmax(dim=1).item()
            label = _categories[class_idx]
            confidence = probs[0][class_idx].item()

            result = {
                "label": label,
                "confidence": confidence,
                "class_index": class_idx,
            }

            job.status = "done"
            job.result = json.dumps(result)
            job.completed_at = datetime.now(timezone.utc)
            logger.info(
                "classify_image_task succeeded for job_id=%s: %s", job_id, result
            )
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            logger.error("classify_image_task failed for job_id=%s: %s", job_id, exc)

        session.add(job)
        session.commit()


class ImageClassificationAdapter(BaseAdapter):
    task_type = "image_classification"
    is_async = True

    def enqueue(self, payload: Dict[str, Any]) -> str:
        job_id = payload.get("job_id")
        if not job_id:
            raise ValueError(
                "ImageClassificationAdapter.enqueue() requires 'job_id' in the "
                "payload - it must be created and committed by the caller "
                "before enqueue() is called, not generated here."
            )

        logger.info("Dispatching classify_image task for job_id=%s", job_id)
        classify_image_task.apply_async(
            kwargs={"job_id": job_id, "image_url": payload["image_url"]},
            task_id=job_id,
        )
        return job_id
