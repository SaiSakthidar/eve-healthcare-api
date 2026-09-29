import logging

from celery import Celery
from sqlalchemy import select

from .config import settings
from .db import SessionLocal
from .models import BookingStatus, Payment, PaymentStatus, PaymentWebhookEvent


logger = logging.getLogger("eve.worker")
celery_app = Celery("eve", broker=settings.celery_broker_url, backend=settings.celery_result_backend)


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def process_payment_webhook(self, event_id: str, provider_reference: str, status: str):
    db = SessionLocal()
    try:
        event = db.scalar(select(PaymentWebhookEvent).where(PaymentWebhookEvent.event_id == event_id))
        if not event:
            return "event_not_reserved"
        payment = db.scalar(select(Payment).where(Payment.provider_reference == provider_reference))
        if not payment:
            raise RuntimeError("Payment not available yet")
        payment.status = status
        payment.booking.status = BookingStatus.CONFIRMED if status == PaymentStatus.SUCCESS else BookingStatus.FAILED
        db.commit()
        logger.info("payment_webhook_applied event_id=%s", event_id)
        return "processed"
    finally:
        db.close()

