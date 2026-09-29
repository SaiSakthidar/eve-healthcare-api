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
sudo docker compose up --build -d
sudo docker compose exec api alembic upgrade head
```

The Compose stack runs the API, PostgreSQL, Redis, and a Celery worker. Webhooks are queued and retried by the worker with exponential backoff.

PostgreSQL is exposed on host port `5433` to avoid conflicts with a local PostgreSQL service; containers continue to use port `5432` internally.

API docs are available at `http://localhost:8000/docs`.

## Endpoints

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

Webhook events are deduplicated by `event_id`.

Centre and test list responses are cached in Redis. Authentication and webhook endpoints are rate limited.

## Example flow

```bash
export API=http://localhost:8000
curl -X POST "$API/auth/signup" -H "Content-Type: application/json" -d '{"email":"demo@example.com","password":"password123"}'
TOKEN=$(curl -s -X POST "$API/auth/login" -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "username=demo@example.com" --data-urlencode "password=password123" | jq -r '.access_token')
AUTH="Authorization: Bearer $TOKEN"
```

Use `POST /centres`, `POST /tests`, and `POST /centres/{centre_id}/tests` to configure availability. Then create a booking with a future ISO-8601 `appointment_at`, call `POST /payments` with `SUCCESS` or `FAILED`, and submit provider updates to `POST /payments/webhook` using a unique `event_id`.

## Data model

- `users`: authenticated patients, uniquely identified by email.
- `diagnostic_centres`: centre name and location.
- `diagnostic_tests`: reusable test catalogue.
- `centre_tests`: centre-specific test availability and price, unique per centre/test pair.
- `bookings`: patient, selected centre/test, appointment time, snapshot amount, and status.
- `payments`: one simulated payment per booking with a unique provider reference.
- `payment_webhook_events`: unique provider event IDs used for idempotency.

## Assumptions

- Any authenticated user may manage centres and tests for this assignment; production code would add roles.
- Payment outcomes are deterministic through the request `outcome` field to make success/failure testing repeatable.
- Webhooks are acknowledged as `queued`; Celery applies the final state asynchronously and retries transient failures.
- A cancelled booking cannot be changed by a webhook.

## If I had more time

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

The suite covers health checks, authentication/booking setup, ownership protection, and webhook idempotency. Manual end-to-end verification has been performed against the Compose stack.
