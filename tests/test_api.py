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


def create_booking(client, headers, test_name="CBC", price="500.00"):
    centre = client.post("/centres", headers=headers, json={"name": f"{test_name} Lab", "location": "Bengaluru"}).json()
    test = client.post("/tests", headers=headers, json={"name": test_name}).json()
    client.post(f"/centres/{centre['id']}/tests", headers=headers, json={"test_id": test["id"], "price": price})
    booking = client.post("/bookings", headers=headers, json={"centre_id": centre["id"], "test_id": test["id"], "appointment_at": "2099-01-01T10:00:00Z"}).json()
    return centre, test, booking


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


def test_centre_detail_includes_priced_tests(client):
    headers = auth(client, "detail@example.com")
    centre, test, _ = create_booking(client, headers, "Vitamin D", "900.00")
    detail = client.get(f"/centres/{centre['id']}").json()
    assert detail["tests"] == [{"test_id": test["id"], "test_name": "Vitamin D", "price": "900.00"}]


def test_failed_payment_marks_booking_failed(client):
    headers = auth(client, "failed@example.com")
    _, _, booking = create_booking(client, headers, "Thyroid")
    payment = client.post("/payments", headers=headers, json={"booking_id": booking["id"], "outcome": "FAILED"})
    assert payment.json()["status"] == "FAILED"
    assert client.get(f"/bookings/{booking['id']}", headers=headers).json()["status"] == "FAILED"


def test_cancellation_prevents_payment(client):
    headers = auth(client, "cancel@example.com")
    _, _, booking = create_booking(client, headers, "HbA1c")
    assert client.post(f"/bookings/{booking['id']}/cancel", headers=headers).json()["status"] == "CANCELLED"
    assert client.post("/payments", headers=headers, json={"booking_id": booking["id"]}).status_code == 409


def test_invalid_booking_and_past_appointment_are_rejected(client):
    headers = auth(client, "invalid@example.com")
    assert client.get("/bookings/99999", headers=headers).status_code == 404
    centre, test, _ = create_booking(client, headers, "Iron")
    response = client.post("/bookings", headers=headers, json={"centre_id": centre["id"], "test_id": test["id"], "appointment_at": "2020-01-01T10:00:00Z"})
    assert response.status_code == 422
