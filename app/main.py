from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import Response

from app.database import create_db_and_tables
from app.routes import admin, health, inference
from app.services.metrics import CONTENT_TYPE_LATEST, MetricsMiddleware, generate_latest


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(title="AI Inference Platform", lifespan=lifespan)

app.add_middleware(MetricsMiddleware)

app.include_router(health.router)
app.include_router(inference.router)
app.include_router(admin.router)


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
