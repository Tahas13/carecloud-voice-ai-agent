"""Pydantic schemas: request/response bodies and the response envelope.

All validation delegates to app/validators.py so the REST API and the voice
agent enforce identical rules.
"""

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

from app import validators as v


class PatientBase(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    sex: str
    phone_number: str
    address_line_1: str
    city: str
    state: str
    zip_code: str

    email: Optional[str] = None
    address_line_2: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: str = "English"
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    # --- validators (shared with the voice agent through app/validators.py) ---
    @field_validator("first_name")
    @classmethod
    def _first_name(cls, val):
        return v.validate_name(val, "first_name")

    @field_validator("last_name")
    @classmethod
    def _last_name(cls, val):
        return v.validate_name(val, "last_name")

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def _dob(cls, val):
        return v.validate_dob(val)

    @field_validator("sex")
    @classmethod
    def _sex(cls, val):
        return v.validate_sex(val)

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, val):
        return v.validate_phone(val)

    @field_validator("email")
    @classmethod
    def _email(cls, val):
        return v.validate_email(val) if val not in (None, "") else None

    @field_validator("address_line_1")
    @classmethod
    def _addr1(cls, val):
        return v.validate_free_text(val, "address_line_1")

    @field_validator("address_line_2")
    @classmethod
    def _addr2(cls, val):
        return v.validate_free_text(val, "address_line_2") if val not in (None, "") else None

    @field_validator("city")
    @classmethod
    def _city(cls, val):
        return v.validate_city(val)

    @field_validator("state")
    @classmethod
    def _state(cls, val):
        return v.validate_state(val)

    @field_validator("zip_code")
    @classmethod
    def _zip(cls, val):
        return v.validate_zip(val)

    @field_validator("insurance_provider")
    @classmethod
    def _ins_provider(cls, val):
        return v.validate_free_text(val, "insurance_provider", 100) if val not in (None, "") else None

    @field_validator("insurance_member_id")
    @classmethod
    def _ins_id(cls, val):
        return v.validate_free_text(val, "insurance_member_id", 50) if val not in (None, "") else None

    @field_validator("preferred_language")
    @classmethod
    def _lang(cls, val):
        return v.validate_free_text(val, "preferred_language", 50) if val not in (None, "") else "English"

    @field_validator("emergency_contact_name")
    @classmethod
    def _ec_name(cls, val):
        return v.validate_name(val, "emergency_contact_name") if val not in (None, "") else None

    @field_validator("emergency_contact_phone")
    @classmethod
    def _ec_phone(cls, val):
        return v.validate_phone(val, "emergency_contact_phone") if val not in (None, "") else None


class PatientCreate(PatientBase):
    """POST /patients body. All required fields must be present."""


class PatientUpdate(PatientBase):
    """PUT /patients/:id body. Partial updates allowed - every field optional."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None
    phone_number: Optional[str] = None
    address_line_1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    preferred_language: Optional[str] = None

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def _dob_optional(cls, val):
        return v.validate_dob(val) if val not in (None, "") else None


class PatientOut(PatientBase):
    model_config = ConfigDict(from_attributes=True)

    patient_id: str
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    @field_serializer("date_of_birth")
    def _serialize_dob(self, value: date) -> str:
        # The assessment specifies MM/DD/YYYY for date_of_birth.
        return value.strftime("%m/%d/%Y")


class CallLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    vapi_call_id: Optional[str] = None
    patient_id: Optional[str] = None
    caller_number: Optional[str] = None
    status: str
    transcript: Optional[str] = None
    summary: Optional[str] = None
    structured_data: Optional[dict] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    ended_reason: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Response envelope: every API response is {"data": ..., "error": ...}
# ---------------------------------------------------------------------------

def envelope(data: Any = None, error: Optional[dict] = None) -> dict:
    return {"data": data, "error": error}


def error_body(code: str, message: str, details: Any = None) -> dict:
    err: dict = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return envelope(data=None, error=err)
