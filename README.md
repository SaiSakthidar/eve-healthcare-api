# EVE Healthcare API

This is my take on the EVE Healthcare backend assignment. It is a small FastAPI service for browsing diagnostic tests, creating bookings, and handling simulated payments without losing consistency when a provider retries a webhook.

I kept the main path deliberately simple, then added the pieces I would expect around it in a real service: PostgreSQL migrations, Redis caching/rate limiting, and a Celery worker for asynchronous webhook handling.

## Quick start

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

For local development you will need PostgreSQL and Redis. Docker Compose is the easiest route; otherwise set the connection variables in `.env` yourself.

Initialize the schema with:

```bash
alembic upgrade head
```

## Run with Docker

```bash
sudo docker compose up --build -d
sudo docker compose exec api alembic upgrade head
```

This starts the API, PostgreSQL, Redis, and a Celery worker. Webhooks are queued first, then processed by the worker with exponential-backoff retries.

PostgreSQL is exposed on host port `5433` to avoid conflicts with a local PostgreSQL service; containers continue to use port `5432` internally.

Swagger is available at `http://localhost:8000/docs` once the stack is up.

## What is included

- `POST /auth/signup`
- `POST /auth/login`
- `GET /health`
- `GET /centres`
- `GET /centres/{centre_id}`
- `POST /centres`
- `PUT /centres/{centre_id}`
- `POST /tests`
- `GET /tests`
- `POST /centres/{centre_id}/tests`
- `POST /bookings`
- `GET /bookings`
- `GET /bookings/{booking_id}`
- `POST /bookings/{booking_id}/cancel`
- `POST /payments`
- `GET /payments/{booking_id}`
- `POST /payments/webhook`

Webhook deliveries are deduplicated by `event_id`. Centre/test list responses are cached in Redis, and the authentication/webhook routes are rate limited.

## A quick API flow

```bash
export API=http://localhost:8000
curl -X POST "$API/auth/signup" -H "Content-Type: application/json" -d '{"email":"demo@example.com","password":"password123"}'
TOKEN=$(curl -s -X POST "$API/auth/login" -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "username=demo@example.com" --data-urlencode "password=password123" | jq -r '.access_token')
AUTH="Authorization: Bearer $TOKEN"
```

From there, create a centre and test, attach a price to that centre, and book a future appointment. `POST /payments` accepts either `SUCCESS` or `FAILED` so the happy and failure paths are both easy to exercise. For webhooks, send a unique `event_id`; retrying the same event is safe.

## Data model, in plain English

- `users`: authenticated patients, uniquely identified by email.
- `diagnostic_centres`: centre name and location.
- `diagnostic_tests`: reusable test catalogue.
- `centre_tests`: centre-specific test availability and price, unique per centre/test pair.
- `bookings`: patient, selected centre/test, appointment time, snapshot amount, and status.
- `payments`: one simulated payment per booking with a unique provider reference.
- `payment_webhook_events`: unique provider event IDs used for idempotency.

## Assumptions I made

- Any authenticated user may manage centres and tests for this assignment; production code would add roles.
- Payment outcomes are deterministic through the request `outcome` field to make success/failure testing repeatable.
- Webhooks are acknowledged as `queued`; Celery applies the final state asynchronously and retries transient failures.
- A cancelled booking cannot be changed by a webhook.

## What I would do next

- Add user roles and administrative audit trails.
- Add availability windows and appointment conflict rules.
- Add webhook signature verification and a durable outbox pattern.
- Add CI that runs PostgreSQL and Redis integration tests on every push.

## Tests

```bash
pytest
```

Integration tests require a PostgreSQL test database:

```bash
TEST_DATABASE_URL=postgresql+psycopg://eve:eve@localhost:5433/eve_test .venv/bin/pytest
```

The suite covers health checks, booking setup, ownership protection, payment failure, cancellation, validation, and webhook idempotency. I also ran the full signup → booking → payment → duplicate-webhook flow against the Compose stack.
