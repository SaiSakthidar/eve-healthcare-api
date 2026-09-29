# EVE Healthcare API

FastAPI backend for diagnostic test bookings and simulated payments.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

PostgreSQL and Redis are required. Start both with Docker Compose or set the connection variables in `.env`.

Initialize the schema with:

```bash
alembic upgrade head
```

## Run with Docker

```bash
docker compose up --build
```

The Compose stack runs the API, PostgreSQL, Redis, and a Celery worker. Webhooks are queued and retried by the worker with exponential backoff.

API docs are available at `http://localhost:8000/docs`.

## Endpoints

- `POST /auth/signup`
- `POST /auth/login`
- `GET /health`
- `GET /centres`
- `POST /centres`
- `POST /tests`
- `POST /centres/{centre_id}/tests`
- `POST /bookings`
- `GET /bookings`
- `POST /payments`
- `GET /payments/{booking_id}`
- `POST /payments/webhook`

Webhook events are deduplicated by `event_id`.

Centre and test list responses are cached in Redis. Authentication and webhook endpoints are rate limited.

## Tests

```bash
pytest
```

Integration tests require a PostgreSQL test database:

```bash
TEST_DATABASE_URL=postgresql+psycopg://eve:eve@localhost:5432/eve_test .venv/bin/pytest
```
