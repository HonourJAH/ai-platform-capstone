# AI Platform (Capstone)

A production-shaped platform that unifies four ML services — text classification, image classification, RAG, and LLM chat — behind a single authenticated, rate-limited, observable inference gateway. Built with FastAPI, Celery, Redis, PostgreSQL, Prometheus, and Grafana.

---

## How It Works

```
POST /inference                    →  unified entry point for all four task types:
                                        text_classification  → sync, returns result immediately
                                        rag_query             → sync, returns result immediately
                                        llm_chat               → sync, returns result immediately
                                        image_classification  → async, returns a job_id

GET    /inference/jobs/{job_id}    →  poll an async job's status/result

POST   /admin/users                →  create a user (admin key required)
POST   /admin/users/{id}/keys      →  mint an API key for that user (shown once)
GET    /admin/users/{id}/keys      →  list a user's keys (hash never exposed)
DELETE /admin/keys/{id}            →  revoke a key

GET    /health                     →  liveness
GET    /metrics                    →  Prometheus scrape endpoint
```

---

## Table of Contents

- [Why Split Sync and Async by Task?](#why-split-sync-and-async-by-task)
- [Auth Model](#auth-model)
- [Rate Limiting](#rate-limiting)
- [Observability](#observability)
- [Model Adapters](#model-adapters)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Running Tests](#running-tests)
- [API Endpoints](#api-endpoints)
- [Request & Response Schemas](#request--response-schemas)
- [Example Usage](#example-usage)
- [Docker](#docker)
- [CI](#ci)
- [Deployment](#deployment)

---

## Why Split Sync and Async by Task?

Text classification, RAG, and LLM chat return in well under a second, so they're handled inline — the client gets a result in the same request/response cycle. Image classification runs a CPU-bound ResNet50 forward pass, which would block the request worker for multiple seconds under load. Instead, `/inference` dispatches it to a Celery queue and returns a `job_id` immediately; the client polls `/inference/jobs/{job_id}` for the result once it's ready.

This mirrors the real decision every ML serving platform has to make: which models are cheap enough to serve synchronously, and which need to go through a background job queue instead.

---

## Auth Model

API keys only — no separate login or dashboard. An admin bootstrap key (`ADMIN_BOOTSTRAP_KEY`) protects every `/admin/*` route, which is how users and their API keys get created. Only the SHA-256 hash of each key is ever stored; the raw key is returned exactly once, at creation time, and can't be retrieved again — only revoked and replaced.

SHA-256 rather than bcrypt is a deliberate choice: the raw key already carries ~256 bits of entropy from `secrets.token_urlsafe(32)`, so there's no weak-password brute-force risk to slow down for, and `get_api_key_user` runs on every single `/inference` call — a fast, deterministic hash keeps that lookup cheap.

---

## Rate Limiting

Token bucket, implemented as a single atomic Redis Lua script so concurrent requests from the same user can't race each other between reading and decrementing the bucket. Two tiers ship by default:

| Tier | Capacity | Refill | Window |
| ---- | -------- | ------ | ------ |
| free | 10       | 10     | 60s    |
| pro  | 100      | 100    | 60s    |

Exceeding the limit returns `429` with a `Retry-After` header telling the client exactly how long to wait.

---

## Observability

`/metrics` exposes Prometheus counters and histograms for request volume, latency (broken out by `task_type`), and rate-limit rejections (by tier) — recorded explicitly inside the `/inference` route, since `task_type` lives in the request body, not the URL path, so generic middleware alone can't see it. A separate, fully generic `HTTP_REQUEST_*` pair of metrics covers every route via middleware.

A Grafana dashboard is auto-provisioned via `docker-compose` — request rate, p95 latency, rejection rate, and HTTP status codes — with zero manual setup required after `docker compose up`.

---

## Model Adapters

| Adapter                  | Status                                                                                                                                                                                          |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `text_classification`     | Real, trained scikit-learn model (TF-IDF + Logistic Regression). Fully functional out of the box.                                                                                                 |
| `image_classification`    | Real, pretrained PyTorch ResNet50 (ImageNet weights via torchvision), run asynchronously through a Celery worker. Downloads the image from the given URL with a `User-Agent` header set, since some hosts block anonymous/bot-like requests. |
| `rag_query` / `llm_chat`  | Correct request/response shape and a real call to Ollama; the RAG retrieval step is a placeholder pending integration with the Qdrant-backed retrieval from an earlier project.                  |

Every adapter implements a common `BaseAdapter` interface (`run()` for sync, `enqueue()` for async) via a registry keyed by `task_type` — the router never branches on task type directly, so adding a fifth model later means adding one adapter and one registry entry, not touching the route.

---

## Project Structure

```
ai-platform-capstone/
├── .github/
│   └── workflows/
│       └── ci.yml                     — GitHub Actions CI: tests + real Postgres/Redis container health check
├── alembic/
│   ├── env.py                          — points Alembic at SQLModel metadata + app settings
│   └── versions/                       — migration history
├── app/
│   ├── main.py                         — FastAPI app, lifespan, /metrics
│   ├── config.py                       — Settings loaded from environment
│   ├── database.py                     — engine + session dependency
│   ├── celery_app.py                   — Celery app + task module registration
│   ├── models/                         — User, APIKey, RequestLog, AsyncJob (SQLModel)
│   ├── schemas/                        — discriminated-union inference schema, admin key schemas
│   ├── routes/                         — /inference, /admin, /health
│   └── services/
│       ├── auth.py                     — API key generation, hashing, verification
│       ├── rate_limit.py               — Redis token bucket (Lua script)
│       ├── metrics.py                  — Prometheus counters/histograms + middleware
│       └── adapters/
│           ├── base.py                 — BaseAdapter interface
│           ├── text_classifier.py      — real sklearn model
│           ├── image_classifier.py     — real ResNet50, Celery task
│           ├── rag.py                  — Ollama call, retrieval placeholder
│           ├── llm_chat.py             — Ollama call
│           └── __init__.py             — adapter registry
├── docker/
│   ├── Dockerfile                      — multi-stage, non-root, HEALTHCHECK
│   ├── start.sh                        — migrate then serve
│   ├── prometheus.yml                  — scrape config
│   └── grafana/provisioning/           — auto-registered datasource + dashboard
├── tests/
│   ├── conftest.py                     — SQLite + fakeredis fixtures, dependency overrides
│   ├── test_auth_service.py
│   ├── test_rate_limiter.py
│   ├── test_inference_integration.py
│   └── test_async_jobs.py
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

---

## Requirements

- Python 3.12+
- Docker and Docker Compose
- [Ollama](https://ollama.com) installed and running **on your host machine** (not containerized — see [Docker](#docker)) if you want `rag_query`/`llm_chat` to actually reach a model
- PostgreSQL and Redis — provided by `docker-compose`, no separate install needed

---

## Getting Started

### 1. Clone the repository

```
git clone https://github.com/HonourJAH/ai-platform-capstone.git
cd ai-platform-capstone
```

### 2. Set up environment variables

```
cp .env.example .env
```

Defaults work as-is for local development; change `ADMIN_BOOTSTRAP_KEY` if you want a real secret rather than the placeholder.

### 3. Start the full stack

```
docker compose up --build
```

This starts: the API (`:8000`), a Celery worker, Postgres, Redis, Prometheus (`:9090`), and Grafana (`:3000`, login `admin`/`admin`). Postgres and Redis are **not** exposed to the host — only reachable inside the Docker network — so a local Postgres/Redis install can run alongside this stack without port conflicts.

### 4. Bootstrap a user and API key

```
curl -X POST localhost:8000/admin/users \
  -H "x-admin-key: change-me-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "tier": "free"}'

curl -X POST localhost:8000/admin/users/1/keys \
  -H "x-admin-key: change-me-admin-key"
```

Copy the `raw_key` from the response — it's shown exactly once.

---

## Environment Variables

| Variable              | Default                                                         | Description                              |
| ----------------------- | ------------------------------------------------------------------ | ------------------------------------------ |
| `DATABASE_URL`           | `postgresql://postgres:postgrespassword@localhost/ai_platform`      | Postgres connection                        |
| `REDIS_URL`              | `redis://localhost:6379/0`                                          | Rate limiter's Redis DB                    |
| `CELERY_BROKER_URL`      | `redis://localhost:6379/1`                                          | Celery broker (separate Redis DB index)    |
| `CELERY_RESULT_BACKEND`  | `redis://localhost:6379/1`                                          | Celery result backend                      |
| `ADMIN_BOOTSTRAP_KEY`    | `change-me-admin-key`                                               | **Change this in any real deployment.**    |

> **In Docker**, `docker-compose.yml` overrides these to use the internal service hostnames (`postgres`, `redis`) rather than `localhost` — containers reach each other by Compose service name, not by host loopback.

---

## Running Tests

Nothing here requires a live Postgres or Redis — every dependency is swapped for an in-memory SQLite DB and `fakeredis` via FastAPI's `dependency_overrides`, and the Celery dispatch is mocked for the async image-classification path.

```
pip install -r requirements-dev.txt
pytest tests/ -v
```

15 tests: API key generation/hashing, token-bucket rate limiting (capacity, per-user isolation, tier config), full auth → rate-limit → inference request flow, and async job creation/ownership checks.

---

## API Endpoints

| Method   | Endpoint                      | Auth       | Description                                  |
| -------- | ------------------------------ | ---------- | --------------------------------------------- |
| `POST`   | `/inference`                    | API key    | Run or queue inference for any task type      |
| `GET`    | `/inference/jobs/{job_id}`      | API key    | Poll an async job's status/result             |
| `POST`   | `/admin/users`                  | Admin key  | Create a user                                 |
| `POST`   | `/admin/users/{user_id}/keys`   | Admin key  | Mint an API key for a user                    |
| `GET`    | `/admin/users/{user_id}/keys`   | Admin key  | List a user's keys (no raw key exposed)       |
| `DELETE` | `/admin/keys/{key_id}`          | Admin key  | Revoke a key                                  |
| `GET`    | `/health`                       | None       | Liveness                                      |
| `GET`    | `/metrics`                      | None       | Prometheus scrape target                      |

---

## Request & Response Schemas

### `POST /inference`

Request body is a discriminated union — `task_type` determines which other fields are required:

```
{"task_type": "text_classification", "text": "this is great"}
{"task_type": "image_classification", "image_url": "https://..."}
{"task_type": "rag_query", "query": "what does the document say about X?"}
{"task_type": "llm_chat", "message": "hello"}
```

**Sync response:**

```
{
  "task_type": "text_classification",
  "status": "completed",
  "result": {"label": "positive", "confidence": 0.87},
  "job_id": null
}
```

**Async response:**

```
{
  "task_type": "image_classification",
  "status": "queued",
  "result": null,
  "job_id": "1b03fa02-f885-4c72-9ec2-1db3061166ff"
}
```

### `GET /inference/jobs/{job_id}`

```
{
  "job_id": "1b03fa02-f885-4c72-9ec2-1db3061166ff",
  "status": "done",
  "result": "{\"label\": \"tabby cat\", \"confidence\": 0.91, \"class_index\": 281}",
  "error": null
}
```

Returns `404` — deliberately, not `403` — if the job doesn't exist *or* belongs to a different user, so a caller can't distinguish "wrong ID" from "someone else's job" by response code alone.

---

## Example Usage

### Text classification (sync)

```
curl -X POST localhost:8000/inference \
  -H "x-api-key: sk_live_..." \
  -H "Content-Type: application/json" \
  -d '{"task_type": "text_classification", "text": "this is great"}'
```

### Image classification (async — queue then poll)

```
curl -X POST localhost:8000/inference \
  -H "x-api-key: sk_live_..." \
  -H "Content-Type: application/json" \
  -d '{"task_type": "image_classification", "image_url": "https://upload.wikimedia.org/wikipedia/commons/3/3a/Cat03.jpg"}'

curl localhost:8000/inference/jobs/<job_id> -H "x-api-key: sk_live_..."
```

### Triggering the rate limit

```
for i in $(seq 1 11); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/inference \
    -H "x-api-key: sk_live_..." \
    -H "Content-Type: application/json" \
    -d '{"task_type": "text_classification", "text": "fine"}'
done
```

The 11th call on a free-tier key returns `429`.

---

## Docker

### Why Postgres and Redis aren't exposed to the host

`api` and `worker` reach `postgres`/`redis` by Compose service name over the internal Docker network — they never need a host port mapping to do that. Leaving `ports:` off `postgres` specifically avoids a real conflict this project hit during development: a locally-installed Postgres already claiming `5432` on the host blocks the containerized one from binding the same port. Redis is still exposed (`6379`), mainly for local debugging convenience with `redis-cli`.

### Why the image includes torch/torchvision

`image_classification` runs a real pretrained ResNet50. The Dockerfile installs the CPU-only PyTorch wheel via its dedicated index URL and pre-downloads the ImageNet weights at *build* time (`RUN python3 -c "...resnet50(weights=ResNet50_Weights.DEFAULT)"`), so the image is self-contained and doesn't hit the network on every container start. This does make the image noticeably larger, and `api` carries torch around even though only `worker` uses it — a reasonable simplification for a single-Dockerfile setup; splitting into a lean `api` image and a heavier `worker` image is the natural next step if image size ever becomes a real constraint.

### Run with Docker Compose

```
docker compose up --build
```

### Stop

```
docker compose down
```

Add `-v` only when you intentionally want to wipe Postgres/Grafana's persisted data — it deletes the named volumes.

---

## CI

GitHub Actions runs on every push/PR to `main`:

1. Installs dependencies, runs the full test suite against SQLite + `fakeredis`.
2. Builds the Docker image, spins up **real** Postgres and Redis as GitHub Actions `services:`, runs the container against them with `--network host`, and polls the container's own `HEALTHCHECK` status until it reports `healthy` — verifying migrations and startup genuinely succeed against a live database, not just that the image builds.

---

## Deployment

- Web service: this repo's `docker/Dockerfile`
- Managed Postgres and managed Key-Value (Redis-compatible) add-ons
- A second worker-type service running `celery -A app.celery_app worker` against the same Redis instance

Render's free/starter tiers don't provide a place to run Prometheus and Grafana as long-lived scrapers, so the observability stack runs locally via `docker-compose`, pointed at the deployed Render URL — a central-Prometheus-scraping-remote-services pattern that's common in real deployments with more services than dashboards.

---

## License

MIT
