"""Vapi webhook: the bridge between the voice agent and the data layer.

Vapi POSTs server messages here:

* ``tool-calls``          -> dispatch to a tool handler, reply with
                             ``{"results": [{"toolCallId", "result" | "error"}]}``
* ``end-of-call-report``  -> persist transcript/summary/structured data.
* ``status-update``       -> logged only.

Every tool result is a plain string written for an LLM to read aloud or act
on. Security: requests must carry the shared secret in ``X-Vapi-Secret``.
"""

import json
import logging
import re
import uuid as uuid_lib
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import validators as v
from app.config import get_settings
from app.database import get_db
from app.schemas import PatientCreate, PatientUpdate
from app.services import patient_service
from app.services.call_service import save_end_of_call_report

router = APIRouter(prefix="/vapi", tags=["vapi"])
logger = logging.getLogger("carecloud.vapi")
settings = get_settings()


# ---------------------------------------------------------------------------
# Tool handlers. Each returns a string the LLM uses to continue the call.
# ---------------------------------------------------------------------------

def _format_validation_errors(exc: ValidationError) -> str:
    problems = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err["loc"]) or "input"
        msg = err["msg"].removeprefix("Value error, ")
        problems.append(f"{field}: {msg}")
    return (
        "VALIDATION FAILED. Do not save yet. Re-ask the caller for ONLY these fields: "
        + " | ".join(problems)
    )


def _patient_summary(p) -> str:
    return (
        f"{p.first_name} {p.last_name}, DOB {p.date_of_birth.strftime('%m/%d/%Y')}, "
        f"phone {p.phone_number}, address {p.address_line_1}"
        f"{', ' + p.address_line_2 if p.address_line_2 else ''}, "
        f"{p.city}, {p.state} {p.zip_code}"
    )


def tool_lookup_patient_by_phone(db: Session, args: dict) -> str:
    try:
        phone = v.validate_phone(args.get("phone_number", ""))
    except ValueError as exc:
        return f"Invalid phone number: {exc}"
    patient = patient_service.find_by_phone(db, phone)
    if patient is None:
        return "No existing patient found with that phone number. Proceed with new registration."
    return (
        f"EXISTING PATIENT FOUND: patient_id={patient.patient_id}. "
        f"Record: {_patient_summary(patient)}. "
        f"Ask the caller: 'It looks like we already have a record for {patient.first_name} "
        f"{patient.last_name}. Would you like to update your information instead?' "
        "If they want to update, use the update_patient tool with this patient_id. "
        "If it is a different person, proceed with a new registration."
    )


def tool_validate_patient_field(db: Session, args: dict) -> str:
    field = str(args.get("field", "")).strip()
    value = args.get("value", "")
    validator = v.FIELD_VALIDATORS.get(field)
    if validator is None:
        return f"Unknown field '{field}'. Valid fields: {', '.join(v.FIELD_VALIDATORS)}."
    try:
        normalized = validator(value)
    except ValueError as exc:
        return f"INVALID: {exc} Politely re-ask the caller for {field}."
    return f"VALID. Normalized value for {field}: {normalized}"


def tool_register_patient(db: Session, args: dict) -> str:
    try:
        data = PatientCreate(**{k: val for k, val in args.items() if val not in (None, "")})
    except ValidationError as exc:
        return _format_validation_errors(exc)

    # Duplicate detection: same phone number already registered.
    existing = patient_service.find_by_phone(db, data.phone_number)
    if existing is not None and not args.get("allow_duplicate"):
        return (
            f"DUPLICATE PHONE NUMBER: we already have {existing.first_name} {existing.last_name} "
            f"(patient_id={existing.patient_id}) with this phone number. Ask the caller whether "
            "they want to update the existing record (use update_patient) or register a separate "
            "new patient anyway (call register_patient again with allow_duplicate=true)."
        )

    try:
        patient = patient_service.create_patient(db, data)
    except Exception:
        logger.exception("Database write failed during register_patient")
        return (
            "DATABASE ERROR: the record could not be saved. Apologize to the caller, "
            "tell them the registration could not be completed right now, and offer to try once more."
        )

    logger.info(
        "REGISTERED PATIENT %s: %s",
        patient.patient_id,
        json.dumps({k: str(val) for k, val in args.items()}),
    )
    return (
        f"SUCCESS: patient registered with patient_id={patient.patient_id}. "
        f"Tell the caller: 'You're all set, {patient.first_name}.' Then offer to schedule "
        "a first appointment before ending the call."
    )


def tool_update_patient(db: Session, args: dict) -> str:
    patient_id = str(args.get("patient_id", "")).strip()
    try:
        patient_id = str(uuid_lib.UUID(patient_id))
    except ValueError:
        return "INVALID patient_id: it must be the UUID returned by lookup_patient_by_phone."
    patient = patient_service.get_patient(db, patient_id)
    if patient is None:
        return "No patient found with that patient_id. Use lookup_patient_by_phone first."

    updates = {k: val for k, val in args.items() if k != "patient_id" and val not in (None, "")}
    if not updates:
        return "No fields to update were provided. Ask the caller what they would like to change."
    try:
        data = PatientUpdate(**updates)
    except ValidationError as exc:
        return _format_validation_errors(exc)

    try:
        patient = patient_service.update_patient(db, patient, data)
    except Exception:
        logger.exception("Database write failed during update_patient")
        return (
            "DATABASE ERROR: the update could not be saved. Apologize and offer to try once more."
        )

    logger.info("UPDATED PATIENT %s fields=%s", patient.patient_id, list(updates))
    return (
        f"SUCCESS: record updated for {patient.first_name} {patient.last_name}. "
        f"Current record: {_patient_summary(patient)}."
    )


_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def tool_schedule_appointment(db: Session, args: dict) -> str:
    """Bonus: mock appointment scheduling. No real calendar behind it.

    Honors the requested weekday (next occurrence) and requested hour when we
    can parse them, so the read-back matches what the caller asked for.
    """
    preferred_day = str(args.get("preferred_day", "")).strip()
    preferred_time = str(args.get("preferred_time", "")).strip()

    # Next occurrence of the requested weekday; otherwise 3 days out.
    slot_date = date.today() + timedelta(days=3)
    for idx, day_name in enumerate(_WEEKDAYS):
        if day_name in preferred_day.lower():
            days_ahead = (idx - date.today().weekday()) % 7 or 7
            slot_date = date.today() + timedelta(days=days_ahead)
            break

    # Use the requested hour if stated; otherwise map morning/afternoon.
    hour_match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?", preferred_time.lower())
    if hour_match:
        hour = int(hour_match.group(1))
        minute = int(hour_match.group(2) or 0)
        meridiem = (hour_match.group(3) or "").replace(".", "")
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif not meridiem and hour < 8:  # bare "2" almost always means 2 PM
            hour += 12
    elif "morn" in preferred_time.lower():
        hour, minute = 10, 0
    else:
        hour, minute = 14, 30
    slot_time = f"{(hour - 12) if hour > 12 else hour}:{minute:02d} {'PM' if hour >= 12 else 'AM'}"

    confirmation = f"APT-{uuid_lib.uuid4().hex[:6].upper()}"
    return (
        f"APPOINTMENT BOOKED (mock): {slot_date.strftime('%A, %B %d')} at {slot_time}. "
        f"Confirmation code {confirmation}. "
        "Read the date, time, and confirmation code back to the caller."
    )


TOOL_HANDLERS = {
    "lookup_patient_by_phone": tool_lookup_patient_by_phone,
    "validate_patient_field": tool_validate_patient_field,
    "register_patient": tool_register_patient,
    "update_patient": tool_update_patient,
    "schedule_appointment": tool_schedule_appointment,
}


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

def _extract_tool_calls(message: dict) -> list[dict]:
    """Normalize the shapes Vapi uses for tool calls.

    Depending on model/provider, each item exposes arguments as ``arguments``,
    ``parameters``, or nested under ``function``.
    """
    calls = []
    for item in message.get("toolCallList") or []:
        func = item.get("function") or {}
        name = item.get("name") or func.get("name")
        args = item.get("arguments") or item.get("parameters") or func.get("arguments") or func.get("parameters") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        calls.append({"id": item.get("id"), "name": name, "arguments": args})
    return calls


@router.post("/webhook")
async def vapi_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_vapi_secret: str = Header(default=""),
):
    body = await request.json()
    message = body.get("message") or {}
    msg_type = message.get("type", "")

    # Vapi reliably forwards the per-tool `server.secret` on tool-calls, but
    # (observed in testing) sends an empty X-Vapi-Secret on assistant-level
    # messages like end-of-call-report. So: strictly authenticate tool-calls
    # (they mutate patient data); accept analysis-only messages that merely
    # append call logs, logging a warning when the secret is absent.
    secret_ok = not settings.vapi_webhook_secret or x_vapi_secret == settings.vapi_webhook_secret
    if not secret_ok:
        if msg_type == "tool-calls" or msg_type == "":
            raise HTTPException(status_code=401, detail="Invalid webhook secret.")
        logger.warning("Vapi message type=%s arrived without a valid secret; accepting (log-only message).", msg_type)

    if msg_type == "tool-calls":
        results = []
        for call in _extract_tool_calls(message):
            handler = TOOL_HANDLERS.get(call["name"])
            logger.info("TOOL CALL %s args=%s", call["name"], json.dumps(call["arguments"]))
            if handler is None:
                results.append({"toolCallId": call["id"], "error": f"Unknown tool {call['name']}"})
                continue
            try:
                result = handler(db, call["arguments"])
                results.append({"toolCallId": call["id"], "result": result})
            except Exception:
                logger.exception("Tool %s crashed", call["name"])
                results.append(
                    {
                        "toolCallId": call["id"],
                        "error": "Internal error while processing this request. Apologize to the caller.",
                    }
                )
            logger.info("TOOL RESULT %s -> %s", call["name"], results[-1].get("result") or results[-1].get("error"))
        return {"results": results}

    if msg_type == "end-of-call-report":
        save_end_of_call_report(db, message)
        return {}

    if msg_type == "status-update":
        logger.info(
            "CALL STATUS %s call_id=%s",
            message.get("status"),
            (message.get("call") or {}).get("id"),
        )
        return {}

    logger.debug("Ignoring Vapi message type=%s", msg_type)
    return {}
