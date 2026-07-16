# builder stage: install dependencies into a venv
FROM python:3.12-slim AS builder

WORKDIR /build

RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# final stage: copy venv + app code only, no build tools
FROM python:3.12-slim

RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
COPY docker/start.sh .
RUN chmod +x start.sh

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["./start.sh"]
