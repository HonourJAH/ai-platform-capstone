# AI Inference Platform (Capstone)

A production-shaped platform that unifies four ML services — text classification, image classification, RAG, and LLM chat — behind a single authenticated, rate-limited, observable inference gateway. Built with FastAPI, Celery, Redis, PostgreSQL, Qdrant, Prometheus, and Grafana.

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
- [Model Adapters — What's Real vs. Placeholder](#model-adapters--whats-real-vs-placeholder)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Running Tests](#running-tests)
- [API Endpoints](#api-endpoints)
- [Request & Response Schemas](#request--response-schemas)
- [Example Usage](#example-usage)
- [Docker](#docker)
- [Known Issues & Startup Fragility](#known-issues--startup-fragility)
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

## Model Adapters — What's Real vs. Placeholder

This platform's focus is the serving layer — auth, rate limiting, async job handling, observability — not the models themselves. Each adapter is documented honestly below rather than glossed over:

| Adapter                  | Status | Details |
| ------------------------- | ------ | ------- |
| `image_classification`    | **Real** | Pretrained PyTorch ResNet50 (ImageNet weights via torchvision), run asynchronously through a Celery worker. Downloads the image from the given URL with a `User-Agent` header set, since some hosts (e.g. Wikimedia) block anonymous/bot-like requests without one. This is the adapter that actually exercises the async job queue, so it's the one that matters most for demonstrating the platform's core design. |
| `text_classification`     | **Placeholder** | A real, functioning scikit-learn model (TF-IDF + Logistic Regression) — but trained on only 6 hardcoded example sentences at import time, not a real dataset. It *will* run genuine inference and return a genuine label + confidence score, but its accuracy on anything outside that tiny vocabulary is close to a coin flip. This is standing in for a properly trained model from an earlier project; swap the training block for a loaded `joblib` artifact to make it production-quality. |
| `rag_query`                | **Partial** | Real embedding model (`all-MiniLM-L6-v2` via sentence-transformers), real Qdrant vector search, and a real call to Ollama for generation — the full RAG pipeline genuinely runs end-to-end. What's missing: this platform has no document-ingestion endpoint, so Qdrant's `documents` collection starts empty. Until it's populated (e.g. by pointing it at an existing document-ingestion pipeline), answers will have no real context to draw from and the model will mostly fall back to "I don't have enough information to answer that." |
| `llm_chat`                 | **Real, dependency-gated** | A real, direct call to Ollama — no placeholder logic. Requires Ollama running and reachable (`host.docker.internal:11434` from inside Docker) with the configured model pulled; without that, this adapter will fail at request time with a connection error, not silently return a fake answer. |

Every adapter implements a common `BaseAdapter` interface (`run()` for sync, `enqueue()` for async) via a registry keyed by `task_type` — the router never branches on task type directly, so adding a fifth model later means adding one adapter and one registry entry, not touching the route.

---

## Project Structure

```
ai-platform-capstone/
├── .github/
│   └── workflows/
│       └── ci.yml                     — GitHub Actions CI: tests (with torch/torchvision) + real Postgres/Redis container health check
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
│           ├── text_classifier.py      — placeholder sklearn model (see table above)
│           ├── image_classifier.py     — real ResNet50, Celery task, structured logging
│           ├── rag.py                  — real embed + Qdrant search + Ollama generate
│           ├── llm_chat.py             — real Ollama call
│           └── __init__.py             — adapter registry
├── docker/
│   ├── Dockerfile                      — multi-stage, non-root, HEALTHCHECK, pre-downloads model weights at build time
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
- PostgreSQL, Redis, and Qdrant — all provided by `docker-compose`, no separate install needed

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

Defaults work as-is for local development; change `ADMIN_BOOTSTRAP_KEY` if you want a real secret rather than the placeholder. Note: values set in `docker-compose.yml`'s `environment:` blocks take precedence over `.env` when running via Compose — see [Environment Variables](#environment-variables) for the full precedence order.

### 3. Start the full stack

```
docker compose up --build
```

The first build will take a while — it pre-downloads the ResNet50 and sentence-transformer model weights at build time so containers don't hit the network on every start. This starts: the API (`:8000`), a Celery worker, Postgres, Redis, Qdrant (`:6333`), Prometheus (`:9090`), and Grafana (`:3000`, login `admin`/`admin`). Postgres, Redis, and Qdrant are reachable only inside the Docker network by default — Postgres specifically has no host port mapping, so a local Postgres install can run alongside this stack without a port conflict.

### 4. Bootstrap a user and API key

```
curl -X POST localhost:8000/admin/users \
  -H "x-admin-key: admin-key" \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "tier": "free"}'

curl -X POST localhost:8000/admin/users/1/keys \
  -H "x-admin-key: admin-key"
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
| `ADMIN_BOOTSTRAP_KEY`    | `admin-key`                                               | **Change this in any real deployment.**    |
| `QDRANT_HOST`            | `localhost`                                                          | Qdrant connection                          |
| `QDRANT_PORT`            | `6333`                                                               | Qdrant connection                          |
| `RAG_COLLECTION_NAME`    | `documents`                                                          | Qdrant collection queried by `rag_query`   |
| `OLLAMA_URL`             | `http://host.docker.internal:11434/api/generate`                    | Reaches Ollama on the Docker host           |
| `OLLAMA_MODEL`           | `llama3.2`                                                           | Must be pulled locally via `ollama pull`   |

**Precedence when running via `docker compose`**: an actual environment variable set on your host (or via `${VAR:-default}` in `docker-compose.yml` itself) always wins over the Python-level default in `app/config.py`. `docker-compose.yml` explicitly sets each of these under every service's `environment:` block, so editing `app/config.py`'s defaults alone has no effect when running through Compose — change `.env` (or the compose file directly) instead.

---

## Running Tests

Nothing here requires a live Postgres or Redis — every dependency is swapped for an in-memory SQLite DB and `fakeredis` via FastAPI's `dependency_overrides`, and the Celery dispatch is mocked for the async image-classification path.

### Option A — inside the built Docker image (recommended)

The production image doesn't ship torch/torchvision/sentence-transformers separately from the app itself, and the `image_classification`/`rag_query` adapters import them at module load time — so importing *any* part of the app (including for tests) pulls in the full ML stack. Rather than installing several hundred MB of ML dependencies into your local machine just to run tests, run them inside the already-built image instead, mounting your local `tests/` folder in (it isn't baked into the production image on purpose):

```
docker compose run --rm --user root -v "$(pwd)/tests:/app/tests" api \
  sh -c "pip install pytest fakeredis lupa pytest-asyncio && pytest tests/ -v"
```

`--user root` is needed only because the image drops to a non-root user by default (a deliberate security hardening choice) — this override is safe for a throwaway `--rm` container.

### Option B — locally

```
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
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
  "job_id": "5f6d19b3-5ae6-4ad5-bc6d-248ba5766879"
}
```

### `GET /inference/jobs/{job_id}`

```
{
  "job_id": "5f6d19b3-5ae6-4ad5-bc6d-248ba5766879",
  "status": "done",
  "result": "{\"label\": \"tiger cat\", \"confidence\": 0.36, \"class_index\": 282}",
  "error": null
}
```

Returns `404` — deliberately, not `403` — if the job doesn't exist *or* belongs to a different user, so a caller can't distinguish "wrong ID" from "someone else's job" by response code alone.

---

## Example Usage

### Text classification (sync, placeholder model — see table above)

```
curl -X POST localhost:8000/inference \
  -H "x-api-key: sk_live_..." \
  -H "Content-Type: application/json" \
  -d '{"task_type": "text_classification", "text": "this is great"}'
```

### Image classification (async, real model — queue then poll)

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

`api` and `worker` reach `postgres`/`redis`/`qdrant` by Compose service name over the internal Docker network — they never need a host port mapping to do that. Leaving `ports:` off `postgres` specifically avoids a real conflict this project hit during development: a locally-installed Postgres already claiming `5432` on the host blocks the containerized one from binding the same port. Redis and Qdrant are still exposed (`6379`, `6333`), mainly for local debugging convenience.

### Why the image includes torch/torchvision and sentence-transformers

`image_classification` runs a real pretrained ResNet50; `rag_query` runs a real sentence-transformer for embeddings. The Dockerfile installs the CPU-only PyTorch wheel via its dedicated index URL and pre-downloads both sets of weights at *build* time, so the image is self-contained and doesn't hit the network — or race against a dependency's timeout — on every container start. This does make the image noticeably larger, and `api` carries all of this around even though only `worker` needs the ResNet50 weights — a reasonable simplification for a single-Dockerfile setup; splitting into a lean `api` image and a heavier `worker` image is the natural next step if image size ever becomes a real constraint.

### Redis persistence

Redis runs with `--appendonly yes` and a named volume (`redis_data`), so a queued-but-unprocessed Celery message survives a container restart instead of silently vanishing — see [Known Issues](#known-issues--startup-fragility) for the failure mode this specifically fixes.

### Run with Docker Compose

```
docker compose up --build
```

### Stop

```
docker compose down
```

Add `-v` only when you intentionally want to wipe Postgres/Grafana/Qdrant/Redis's persisted data — it deletes the named volumes.

---

## Known Issues & Startup Fragility

Documented honestly rather than hidden, since these were genuine bugs hit and fixed during development and are worth understanding if you extend this project:

- **Celery must run with `--pool=solo`.** The default `prefork` pool forks child processes from a main process that has already loaded PyTorch — PyTorch's native threading libraries can leave a lock held by a thread that doesn't exist in the forked child, causing the very first model-using task to hang forever with no error. `solo` avoids forking entirely, at the cost of one task at a time.
- **The `AsyncJob` row is created and committed *before* the Celery task is dispatched**, not after — dispatching first can let a fast worker start the task before its own database row exists yet, causing it to silently no-op.
- **`enqueue()` never generates its own job ID.** It strictly uses the `job_id` passed in from the route (which already created and committed the corresponding `AsyncJob` row) and raises immediately if one isn't provided. An earlier version generated its own UUID internally, which meant the ID returned to the client and the ID the Celery task actually looked up in the database could silently diverge — producing jobs that appeared to succeed (in the worker's logs) while the client polled a different, permanently-`"pending"` row forever. If you extend this pattern to a new async adapter, keep job ID generation solely in the route.
- **A single adapter's import-time failure can take down unrelated adapters.** All four adapters are imported together as one package; an unhandled exception during one adapter's module-level setup (e.g. a slow external service) prevents the *entire* package from importing, deregistering every other adapter's Celery task in the process. `rag.py`'s Qdrant setup specifically catches and logs rather than raising, for this reason — worth applying the same pattern to any adapter with a network call at import time.
- **Give every external dependency a real healthcheck, not just `depends_on`.** `depends_on` alone only waits for a container to *start*, not for the service inside it to actually be ready to accept connections — this caused real startup-ordering races against both Postgres and Qdrant during development. Every external service in `docker-compose.yml` now has an explicit `healthcheck:`, and `api`/`worker` wait on `condition: service_healthy`, not just `service_started`.

---

## CI

GitHub Actions runs on every push/PR to `main`:

1. **`test`** — installs the CPU-only torch/torchvision wheel plus `requirements-dev.txt`, then runs the full test suite against SQLite + `fakeredis`. Torch has to be installed explicitly here since it's normally only ever installed inside the Docker build, not via `requirements.txt`.
2. **`build`** (depends on `test` passing) — builds the Docker image, spins up **real** Postgres and Redis as GitHub Actions `services:`, runs the container against them with `--network host`, and polls the container's own `HEALTHCHECK` status until it reports `healthy` — verifying migrations and startup genuinely succeed against a live database, not just that the image builds.

---

## Deployment

- Web service: this repo's `docker/Dockerfile`
- Managed Postgres and managed Key-Value (Redis-compatible) add-ons
- A second worker-type service running `celery -A app.celery_app worker --pool=solo` against the same Redis instance
- A managed or self-hosted Qdrant instance for `rag_query`

Render's free/starter tiers don't provide a place to run Prometheus and Grafana as long-lived scrapers, so the observability stack runs locally via `docker-compose`, pointed at the deployed Render URL — a central-Prometheus-scraping-remote-services pattern that's common in real deployments with more services than dashboards.

---

## License

MIT
