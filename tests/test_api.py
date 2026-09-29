import os

import pytest


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests", allow_module_level=True)

os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(engine)


def auth(client, email="user@example.com"):
    client.post("/auth/signup", json={"email": email, "password": "password123"})
    response = client.post("/auth/login", data={"username": email, "password": "password123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_auth_and_booking_flow(client):
    headers = auth(client)
    centre = client.post("/centres", headers=headers, json={"name": "Central Lab", "location": "Bengaluru"}).json()
    test = client.post("/tests", headers=headers, json={"name": "CBC"}).json()
    client.post(f"/centres/{centre['id']}/tests", headers=headers, json={"test_id": test["id"], "price": "500.00"})
    booking = client.post("/bookings", headers=headers, json={"centre_id": centre["id"], "test_id": test["id"], "appointment_at": "2099-01-01T10:00:00Z"})
    assert booking.status_code == 201
    assert booking.json()["status"] == "PENDING"


def test_duplicate_webhook_is_idempotent(client):
    headers = auth(client, "webhook@example.com")
    centre = client.post("/centres", headers=headers, json={"name": "Webhook Lab", "location": "Pune"}).json()
    test = client.post("/tests", headers=headers, json={"name": "Lipid Profile"}).json()
    client.post(f"/centres/{centre['id']}/tests", headers=headers, json={"test_id": test["id"], "price": "750.00"})
    booking = client.post("/bookings", headers=headers, json={"centre_id": centre["id"], "test_id": test["id"], "appointment_at": "2099-01-01T10:00:00Z"}).json()
    payment = client.post("/payments", headers=headers, json={"booking_id": booking["id"], "outcome": "SUCCESS"}).json()
    event = {"event_id": "event-1", "provider_reference": payment["payment_reference"], "status": "SUCCESS"}
    assert client.post("/payments/webhook", json=event).json() == {"status": "queued"}
    assert client.post("/payments/webhook", json=event).json() == {"status": "already_processed"}


def test_booking_requires_authentication(client):
    response = client.get("/bookings")
    assert response.status_code == 401
