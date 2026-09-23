"""Call log persistence: stores Vapi end-of-call reports linked to patients."""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CallLog
from app.services.patient_service import find_by_phone

logger = logging.getLogger("carecloud.calls")


def _parse_ts(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def save_end_of_call_report(db: Session, message: dict) -> CallLog:
    """Persist a Vapi ``end-of-call-report`` server message.

    Links the call to a patient by (in order of preference) the phone number in
    the analyzed structured data, then the caller ID.
    """
    call = message.get("call") or {}
    analysis = message.get("analysis") or {}
    structured = analysis.get("structuredData") or {}
    customer = call.get("customer") or message.get("customer") or {}
    caller_number = customer.get("number")

    # Link to a patient record if we can.
    patient = None
    for candidate in (structured.get("phone_number"), caller_number):
        if candidate:
            digits = "".join(ch for ch in str(candidate) if ch.isdigit())
            if len(digits) == 11 and digits.startswith("1"):
                digits = digits[1:]
            if len(digits) == 10:
                patient = find_by_phone(db, digits)
                if patient:
                    break

    ended_reason = message.get("endedReason") or ""
    registered = bool(structured.get("registration_completed")) or patient is not None
    dropped_reasons = ("pipeline-error", "customer-did-not-answer", "phone-call-provider")
    if registered:
        status = "completed"
    elif any(r in ended_reason for r in dropped_reasons):
        status = "failed"
    else:
        status = "incomplete"

    existing = None
    vapi_call_id = call.get("id")
    if vapi_call_id:
        existing = db.scalars(select(CallLog).where(CallLog.vapi_call_id == vapi_call_id)).first()

    log = existing or CallLog()
    log.vapi_call_id = vapi_call_id
    log.patient_id = patient.patient_id if patient else None
    log.caller_number = caller_number
    log.status = status
    log.transcript = message.get("transcript")
    log.summary = analysis.get("summary") or message.get("summary")
    log.structured_data = structured or None
    log.started_at = _parse_ts(message.get("startedAt"))
    log.ended_at = _parse_ts(message.get("endedAt"))
    log.ended_reason = ended_reason or None

    if existing is None:
        db.add(log)
    db.commit()
    db.refresh(log)

    # Observability requirement: log the final collected data payload to stdout.
    logger.info(
        "END-OF-CALL call_id=%s status=%s patient_id=%s caller=%s structured_data=%s",
        vapi_call_id, status, log.patient_id, caller_number, structured,
    )
    return log
