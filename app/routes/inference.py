import time

import redis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.database import get_session
from app.models import AsyncJob, RequestLog, User
from app.schemas.inference import InferenceRequest, InferenceResponse
from app.services.adapters import get_adapter
from app.services.auth import get_api_key_user
from app.services.metrics import RATE_LIMIT_REJECTIONS, REQUEST_COUNT, REQUEST_LATENCY
from app.services.rate_limit import RateLimiter, get_redis_client

router = APIRouter(tags=["inference"])


def get_rate_limiter(
    redis_client: redis.Redis = Depends(get_redis_client),
) -> RateLimiter:
    return RateLimiter(redis_client)


@router.post("/inference", response_model=InferenceResponse)
def run_inference(
    payload: InferenceRequest,
    user: User = Depends(get_api_key_user),
    session: Session = Depends(get_session),
    limiter: RateLimiter = Depends(get_rate_limiter),
):
    allowed, tokens_remaining, retry_after = limiter.check(user.id, user.tier)
    if not allowed:
        RATE_LIMIT_REJECTIONS.labels(tier=user.tier).inc()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(int(retry_after))},
        )

    adapter = get_adapter(payload.task_type)
    start = time.perf_counter()
    status_code = status.HTTP_200_OK

    try:
        if adapter.is_async:
            import uuid

            job_id = str(uuid.uuid4())
            job = AsyncJob(id=job_id, user_id=user.id, task_type=payload.task_type)
            session.add(job)
            session.commit()

            adapter.enqueue({**payload.model_dump(), "job_id": job_id})

            response = InferenceResponse(
                task_type=payload.task_type, status="queued", job_id=job_id
            )
        else:
            result = adapter.run(payload.model_dump())
            response = InferenceResponse(
                task_type=payload.task_type, status="completed", result=result
            )

        return response
    except Exception:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        raise
    finally:
        latency_ms = (time.perf_counter() - start) * 1000
        REQUEST_COUNT.labels(task_type=payload.task_type, status_code=status_code).inc()
        REQUEST_LATENCY.labels(task_type=payload.task_type).observe(latency_ms / 1000)

        session.add(
            RequestLog(
                user_id=user.id,
                task_type=payload.task_type,
                status_code=status_code,
                latency_ms=latency_ms,
            )
        )
        session.commit()


@router.get("/inference/jobs/{job_id}")
def get_job_status(
    job_id: str,
    user: User = Depends(get_api_key_user),
    session: Session = Depends(get_session),
):
    job = session.get(AsyncJob, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )

    return {
        "job_id": job.id,
        "status": job.status,
        "result": job.result,
        "error": job.error,
    }
