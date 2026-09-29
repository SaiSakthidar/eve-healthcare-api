from datetime import datetime, timezone
import logging
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import create_token, current_user, hash_password, verify_password
from .cache import get_json, invalidate, set_json
from .config import settings
from .db import get_db
from .models import Booking, BookingStatus, CentreTest, DiagnosticCentre, DiagnosticTest, Payment, PaymentStatus, PaymentWebhookEvent, User
from .schemas import BookingCreate, BookingOut, CentreCreate, CentreDetail, CentreOut, CentreTestCreate, CentreTestOut, CentreUpdate, PaymentCreate, TestCreate, TestOut, Token, UserCreate, UserOut, WebhookIn
from .worker import process_payment_webhook


logger = logging.getLogger("eve.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"], storage_uri=settings.redis_url)
app = FastAPI(title="EVE Healthcare API", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/auth/signup", response_model=UserOut, status_code=201)
@limiter.limit("10/minute")
def signup(request: Request, data: UserCreate, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == data.email.lower())):
        raise HTTPException(409, "Email already registered")
    user = User(email=data.email.lower(), password_hash=hash_password(data.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/login", response_model=Token)
@limiter.limit("10/minute")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    return Token(access_token=create_token(user.id))


@app.post("/centres", response_model=CentreOut, status_code=201)
def create_centre(data: CentreCreate, db: Session = Depends(get_db), _: User = Depends(current_user)):
    centre = DiagnosticCentre(**data.model_dump())
    db.add(centre)
    db.commit()
    db.refresh(centre)
    invalidate("centres:")
    return centre


@app.get("/centres", response_model=list[CentreOut])
def list_centres(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    key = f"centres:{offset}:{limit}"
    cached = get_json(key)
    if cached is not None:
        return cached
    result = list(db.scalars(select(DiagnosticCentre).order_by(DiagnosticCentre.id).offset(offset).limit(limit)))
    payload = [CentreOut.model_validate(item).model_dump() for item in result]
    set_json(key, payload)
    return payload


@app.get("/centres/{centre_id}", response_model=CentreDetail)
def get_centre(centre_id: int, db: Session = Depends(get_db)):
    centre = db.get(DiagnosticCentre, centre_id)
    if not centre:
        raise HTTPException(404, "Centre not found")
    return CentreDetail(id=centre.id, name=centre.name, location=centre.location, tests=[CentreTestOut(test_id=item.test_id, test_name=item.test.name, price=item.price) for item in centre.tests])


@app.put("/centres/{centre_id}", response_model=CentreOut)
def update_centre(centre_id: int, data: CentreUpdate, db: Session = Depends(get_db), _: User = Depends(current_user)):
    centre = db.get(DiagnosticCentre, centre_id)
    if not centre:
        raise HTTPException(404, "Centre not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(centre, field, value)
    db.commit()
    db.refresh(centre)
    invalidate("centres:")
    return centre


@app.post("/tests", response_model=TestOut, status_code=201)
def create_test(data: TestCreate, db: Session = Depends(get_db), _: User = Depends(current_user)):
    test = DiagnosticTest(name=data.name)
    db.add(test)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Test already exists")
    db.refresh(test)
    invalidate("tests:")
    return {"id": test.id, "name": test.name}


@app.get("/tests", response_model=list[TestOut])
def list_tests(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    key = f"tests:{offset}:{limit}"
    cached = get_json(key)
    if cached is not None:
        return cached
    tests = db.scalars(select(DiagnosticTest).order_by(DiagnosticTest.id).offset(offset).limit(limit)).all()
    payload = [{"id": test.id, "name": test.name} for test in tests]
    set_json(key, payload)
    return payload


@app.post("/centres/{centre_id}/tests", status_code=201)
def attach_test(centre_id: int, data: CentreTestCreate, db: Session = Depends(get_db), _: User = Depends(current_user)):
    if not db.get(DiagnosticCentre, centre_id) or not db.get(DiagnosticTest, data.test_id):
        raise HTTPException(404, "Centre or test not found")
    item = CentreTest(centre_id=centre_id, test_id=data.test_id, price=data.price)
    db.add(item)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Test already offered by this centre")
    invalidate("centres:")
    return {"centre_id": centre_id, "test_id": data.test_id, "price": data.price}


@app.post("/bookings", response_model=BookingOut, status_code=201)
def create_booking(data: BookingCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if data.appointment_at <= datetime.now(timezone.utc):
        raise HTTPException(422, "Appointment must be in the future")
    centre_test = db.scalar(select(CentreTest).where(CentreTest.centre_id == data.centre_id, CentreTest.test_id == data.test_id))
    if not centre_test:
        raise HTTPException(404, "Test is not offered by this centre")
    booking = Booking(user_id=user.id, centre_test_id=centre_test.id, appointment_at=data.appointment_at, amount=centre_test.price, status=BookingStatus.PENDING)
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return BookingOut(id=booking.id, centre_id=data.centre_id, test_id=data.test_id, appointment_at=booking.appointment_at, amount=booking.amount, status=booking.status)


@app.get("/bookings", response_model=list[BookingOut])
def list_bookings(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), user: User = Depends(current_user)):
    bookings = db.scalars(select(Booking).where(Booking.user_id == user.id).order_by(Booking.id.desc()).offset(offset).limit(limit)).all()
    return [BookingOut(id=b.id, centre_id=b.centre_test.centre_id, test_id=b.centre_test.test_id, appointment_at=b.appointment_at, amount=b.amount, status=b.status) for b in bookings]


def booking_response(booking: Booking) -> BookingOut:
    return BookingOut(id=booking.id, centre_id=booking.centre_test.centre_id, test_id=booking.centre_test.test_id, appointment_at=booking.appointment_at, amount=booking.amount, status=booking.status)


@app.get("/bookings/{booking_id}", response_model=BookingOut)
def get_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    booking = db.scalar(select(Booking).where(Booking.id == booking_id, Booking.user_id == user.id))
    if not booking:
        raise HTTPException(404, "Booking not found")
    return booking_response(booking)


@app.post("/bookings/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    booking = db.scalar(select(Booking).where(Booking.id == booking_id, Booking.user_id == user.id))
    if not booking:
        raise HTTPException(404, "Booking not found")
    if booking.status not in (BookingStatus.PENDING, BookingStatus.CONFIRMED):
        raise HTTPException(409, "Booking cannot be cancelled")
    booking.status = BookingStatus.CANCELLED
    db.commit()
    db.refresh(booking)
    return booking_response(booking)


@app.post("/payments", status_code=201)
def pay(data: PaymentCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    booking = db.scalar(select(Booking).where(Booking.id == data.booking_id, Booking.user_id == user.id))
    if not booking:
        raise HTTPException(404, "Booking not found")
    if booking.status != BookingStatus.PENDING:
        raise HTTPException(409, "Booking is not payable")
    if db.scalar(select(Payment).where(Payment.booking_id == booking.id)):
        raise HTTPException(409, "Payment already exists for this booking")
    payment = Payment(booking_id=booking.id, provider_reference=f"sim_{uuid4().hex}", status=data.outcome, amount=booking.amount)
    booking.status = BookingStatus.CONFIRMED if data.outcome == PaymentStatus.SUCCESS else BookingStatus.FAILED
    db.add(payment)
    db.commit()
    logger.info("payment_processed booking_id=%s status=%s", booking.id, data.outcome)
    return {"booking_id": booking.id, "payment_reference": payment.provider_reference, "status": payment.status}


@app.get("/payments/{booking_id}")
def get_payment(booking_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    payment = db.scalar(select(Payment).join(Booking).where(Payment.booking_id == booking_id, Booking.user_id == user.id))
    if not payment:
        raise HTTPException(404, "Payment not found")
    return {"booking_id": booking_id, "payment_reference": payment.provider_reference, "status": payment.status, "amount": payment.amount}


@app.post("/payments/webhook")
@limiter.limit("30/minute")
def payment_webhook(request: Request, data: WebhookIn, db: Session = Depends(get_db)):
    if db.scalar(select(PaymentWebhookEvent).where(PaymentWebhookEvent.event_id == data.event_id)):
        return {"status": "already_processed"}
    payment = db.scalar(select(Payment).where(Payment.provider_reference == data.provider_reference))
    if not payment:
        raise HTTPException(404, "Payment not found")
    if payment.booking.status == BookingStatus.CANCELLED:
        raise HTTPException(409, "Booking is cancelled")
    db.add(PaymentWebhookEvent(event_id=data.event_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"status": "already_processed"}
    try:
        process_payment_webhook.delay(data.event_id, data.provider_reference, data.status)
    except Exception:
        db.delete(db.scalar(select(PaymentWebhookEvent).where(PaymentWebhookEvent.event_id == data.event_id)))
        db.commit()
        raise HTTPException(503, "Webhook queue unavailable")
    logger.info("payment_webhook_queued event_id=%s reference=%s status=%s", data.event_id, data.provider_reference, data.status)
    return {"status": "queued"}
