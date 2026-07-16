# AI Inference Platform (Capstone)
##### "sk_live_XRHG3j4i7oQUpGJ3_bLtDPjOB1J1xq2P0KCoYaCam6o"
A production-shaped platform that unifies four previously-built ML services
(text classification, image classification, RAG, and LLM chat) behind a
single authenticated, rate-limited, observable `/inference` endpoint.

## Architecture

```
Client (API key)
      |
Token bucket rate limiter (free/pro tier, Redis-backed)
      |
/inference router
      |
      +--> text_classification (sync)
      +--> rag_query           (sync)
      +--> llm_chat            (sync)
      +--> image_classification (async, via Celery -> job_id -> poll /inference/jobs/{id})
      |
Prometheus /metrics --> Grafana dashboard
```

**Why sync/async is split by task**: text classification and RAG/LLM calls
return in well under a second, so they're handled inline. Image
classification is CPU-heavy (ResNet50) and would block the request worker
for multiple seconds under load, so it's dispatched to a Celery queue
instead - the client gets a `job_id` immediately and polls
`/inference/jobs/{job_id}` for the result. This mirrors how real ML
platforms decide what to serve synchronously vs. as a background job.

## Auth

API keys only - no separate login/dashboard. An admin bootstrap key
(`ADMIN_BOOTSTRAP_KEY`) protects `/admin/*` routes, which create users and
mint/revoke their API keys. Only the SHA-256 hash of each key is stored;
the raw key is shown exactly once, at creation time.

## Rate limiting

Token bucket, implemented as an atomic Redis Lua script (avoids races
between concurrent requests from the same user). Two tiers ship by
default:

| Tier | Capacity | Refill | Window |
|------|----------|--------|--------|
| free | 10       | 10     | 60s    |
| pro  | 100      | 100    | 60s    |

Exceeding the limit returns `429` with a `Retry-After` header.

## Observability

`/metrics` exposes Prometheus counters/histograms for request volume,
latency (by task_type), and rate-limit rejections (by tier). A Grafana
dashboard is auto-provisioned via `docker-compose` with panels for request
rate, p95 latency, rejection rate, and HTTP status codes.

## Local development

```bash
cp .env.example .env
docker-compose up --build
```

This starts: the API (`:8000`), a Celery worker, Postgres, Redis,
Prometheus (`:9090`), and Grafana (`:3000`, login `admin`/`admin`).

Bootstrap a user and key:

```bash
curl -X POST localhost:8000/admin/users \
  -H "x-admin-key: $ADMIN_BOOTSTRAP_KEY" \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "tier": "free"}'

curl -X POST localhost:8000/admin/users/1/keys \
  -H "x-admin-key: $ADMIN_BOOTSTRAP_KEY"
```

Call the unified endpoint:

```bash
curl -X POST localhost:8000/inference \
  -H "x-api-key: sk_live_..." \
  -H "Content-Type: application/json" \
  -d '{"task_type": "text_classification", "text": "this is great"}'
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

Unit tests cover the auth service and rate limiter in isolation (no DB, no
network). Integration tests exercise the full auth -> rate-limit ->
inference flow against an in-memory SQLite DB and fakeredis, with the
Celery dispatch mocked for the async image-classification path.

## Deployment (Render)

- Web service: this repo's `docker/Dockerfile`
- Managed Postgres and managed Key-Value (Redis-compatible) add-ons
- A second worker-type service running `celery -A app.celery_app worker`
  against the same Redis instance

Render's free/starter tiers don't provide a place to run Prometheus and
Grafana as long-lived scrapers, so for now the observability stack runs
locally via `docker-compose`, pointed at the deployed Render URL - a
central-Prometheus-scraping-remote-services pattern that's common in real
deployments with more services than dashboards.

## Notes on the model adapters

The text classifier ships with a small real scikit-learn model trained at
import time so the endpoint is fully functional out of the box. The image
classification, RAG, and LLM chat adapters are wired with the correct
interface, request/response shape, and integration points clearly marked
in `app/services/adapters/` - swap in the model-loading code from Projects
1, 2, 4, and 6 to make them fully live.
