"""Patient data access layer.

Shared by the REST API, the Vapi webhook tools, and the dashboard, so the
telephony layer and the web layer never duplicate persistence logic.
"""

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Patient
from app.schemas import PatientCreate, PatientUpdate


def create_patient(db: Session, data: PatientCreate) -> Patient:
    patient = Patient(**data.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def get_patient(db: Session, patient_id: str, include_deleted: bool = False) -> Optional[Patient]:
    patient = db.get(Patient, patient_id)
    if patient is None:
        return None
    if patient.deleted_at is not None and not include_deleted:
        return None
    return patient


def list_patients(
    db: Session,
    last_name: Optional[str] = None,
    date_of_birth: Optional[date] = None,
    phone_number: Optional[str] = None,
) -> list[Patient]:
    stmt = select(Patient).where(Patient.deleted_at.is_(None))
    if last_name:
        stmt = stmt.where(Patient.last_name.ilike(last_name))
    if date_of_birth:
        stmt = stmt.where(Patient.date_of_birth == date_of_birth)
    if phone_number:
        stmt = stmt.where(Patient.phone_number == phone_number)
    stmt = stmt.order_by(Patient.created_at.desc())
    return list(db.scalars(stmt).all())


def find_by_phone(db: Session, phone_number: str) -> Optional[Patient]:
    """Most recent non-deleted patient with this phone number (duplicate check)."""
    stmt = (
        select(Patient)
        .where(Patient.phone_number == phone_number, Patient.deleted_at.is_(None))
        .order_by(Patient.created_at.desc())
    )
    return db.scalars(stmt).first()


def update_patient(db: Session, patient: Patient, data: PatientUpdate) -> Patient:
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(patient, field, value)
    db.commit()
    db.refresh(patient)
    return patient


def soft_delete_patient(db: Session, patient: Patient) -> Patient:
    patient.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(patient)
    return patient
