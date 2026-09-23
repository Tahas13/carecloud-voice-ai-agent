"""REST API for patient records (assessment section 4).

All responses use the {"data": ..., "error": ...} envelope. Validation errors
surface as 422 via the global handlers in app/main.py; invalid UUIDs are 422,
missing/soft-deleted records are 404.
"""

import uuid as uuid_lib
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import validators as v
from app.database import get_db
from app.schemas import PatientCreate, PatientOut, PatientUpdate, envelope
from app.services import patient_service

router = APIRouter(prefix="/patients", tags=["patients"])


def _validate_uuid(patient_id: str) -> str:
    try:
        return str(uuid_lib.UUID(patient_id))
    except ValueError:
        raise HTTPException(status_code=422, detail="patient_id must be a valid UUID.")


@router.get("")
def list_patients(
    last_name: Optional[str] = Query(None),
    date_of_birth: Optional[str] = Query(None),
    phone_number: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    dob = None
    if date_of_birth:
        try:
            dob = v.validate_dob(date_of_birth)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    phone = None
    if phone_number:
        try:
            phone = v.validate_phone(phone_number)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    patients = patient_service.list_patients(db, last_name=last_name, date_of_birth=dob, phone_number=phone)
    return envelope([PatientOut.model_validate(p).model_dump() for p in patients])


@router.get("/{patient_id}")
def get_patient(patient_id: str, db: Session = Depends(get_db)):
    pid = _validate_uuid(patient_id)
    patient = patient_service.get_patient(db, pid)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    return envelope(PatientOut.model_validate(patient).model_dump())


@router.post("", status_code=201)
def create_patient(body: PatientCreate, db: Session = Depends(get_db)):
    patient = patient_service.create_patient(db, body)
    return envelope(PatientOut.model_validate(patient).model_dump())


@router.put("/{patient_id}")
def update_patient(patient_id: str, body: PatientUpdate, db: Session = Depends(get_db)):
    pid = _validate_uuid(patient_id)
    patient = patient_service.get_patient(db, pid)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    patient = patient_service.update_patient(db, patient, body)
    return envelope(PatientOut.model_validate(patient).model_dump())


@router.delete("/{patient_id}")
def delete_patient(patient_id: str, db: Session = Depends(get_db)):
    pid = _validate_uuid(patient_id)
    patient = patient_service.get_patient(db, pid)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    patient = patient_service.soft_delete_patient(db, patient)
    return envelope(PatientOut.model_validate(patient).model_dump())
