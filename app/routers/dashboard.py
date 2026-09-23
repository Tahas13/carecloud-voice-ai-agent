"""Simple server-rendered dashboard (bonus): view registered patients + calls."""

import uuid as uuid_lib
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import validators as v
from app.config import get_settings
from app.database import get_db
from app.models import CallLog, Patient
from app.services import patient_service

settings = get_settings()

router = APIRouter(prefix="/dashboard", tags=["dashboard"], include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


@router.get("")
def dashboard(
    request: Request,
    q: Optional[str] = Query(None, description="Search by last name or phone"),
    db: Session = Depends(get_db),
):
    last_name = phone = None
    if q:
        digits = "".join(ch for ch in q if ch.isdigit())
        if len(digits) >= 7:
            try:
                phone = v.validate_phone(q)
            except ValueError:
                phone = digits[-10:]
        else:
            last_name = q.strip()

    patients = patient_service.list_patients(db, last_name=last_name, phone_number=phone)
    call_counts = {
        p.patient_id: len([c for c in p.call_logs]) for p in patients
    }
    all_calls = list(db.scalars(select(CallLog).order_by(CallLog.created_at.desc())).all())
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "patients": patients,
            "call_counts": call_counts,
            "recent_calls": all_calls[:10],
            "q": q or "",
            "stats": {
                "patients": len(patients),
                "calls": len(all_calls),
                "completed": sum(1 for c in all_calls if c.status == "completed"),
            },
            "agent_phone": settings.agent_phone_number,
            "agent_phone_tel": "".join(ch for ch in settings.agent_phone_number if ch.isdigit() or ch == "+"),
            "vapi_public_key": settings.vapi_public_key,
            "vapi_assistant_id": settings.vapi_assistant_id,
        },
    )


@router.get("/patients/{patient_id}")
def patient_detail(request: Request, patient_id: str, db: Session = Depends(get_db)):
    try:
        pid = str(uuid_lib.UUID(patient_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Patient not found.")
    patient = db.get(Patient, pid)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found.")
    calls = sorted(patient.call_logs, key=lambda c: c.created_at, reverse=True)
    return templates.TemplateResponse(
        request, "patient_detail.html", {"p": patient, "calls": calls}
    )
