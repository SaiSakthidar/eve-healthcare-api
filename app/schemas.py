from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CentreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    location: str = Field(min_length=1, max_length=255)


class CentreOut(CentreCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


class TestCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CentreTestCreate(BaseModel):
    test_id: int
    price: Decimal = Field(gt=0, decimal_places=2)


class BookingCreate(BaseModel):
    centre_id: int
    test_id: int
    appointment_at: datetime


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    centre_id: int
    test_id: int
    appointment_at: datetime
    amount: Decimal
    status: str


class PaymentCreate(BaseModel):
    booking_id: int
    outcome: Literal["SUCCESS", "FAILED"] = "SUCCESS"


class WebhookIn(BaseModel):
    event_id: str = Field(min_length=1)
    provider_reference: str = Field(min_length=1)
    status: Literal["SUCCESS", "FAILED"]
