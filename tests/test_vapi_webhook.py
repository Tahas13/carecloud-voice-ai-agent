"""Webhook tests: secret enforcement, tool dispatch, end-of-call persistence."""

from sqlalchemy import select

from app.models import CallLog, Patient

HEADERS = {"X-Vapi-Secret": "test-secret"}


def _tool_call(client, name, arguments, headers=HEADERS):
    payload = {
        "message": {
            "type": "tool-calls",
            "toolCallList": [{"id": "call_1", "name": name, "arguments": arguments}],
        }
    }
    return client.post("/vapi/webhook", json=payload, headers=headers)


REGISTRATION_ARGS = {
    "first_name": "Maria",
    "last_name": "Garcia",
    "date_of_birth": "04/12/1985",
    "sex": "Female",
    "phone_number": "3055550142",
    "address_line_1": "789 Palm Ave",
    "city": "Miami",
    "state": "FL",
    "zip_code": "33101",
}


class TestSecurity:
    def test_missing_secret_rejected(self, client):
        resp = _tool_call(client, "validate_patient_field", {"field": "state", "value": "FL"}, headers={})
        assert resp.status_code == 401

    def test_wrong_secret_rejected(self, client):
        resp = _tool_call(
            client, "validate_patient_field", {"field": "state", "value": "FL"},
            headers={"X-Vapi-Secret": "wrong"},
        )
        assert resp.status_code == 401


class TestValidateFieldTool:
    def test_valid_value(self, client):
        resp = _tool_call(client, "validate_patient_field", {"field": "date_of_birth", "value": "04/12/1985"})
        assert resp.status_code == 200
        result = resp.json()["results"][0]
        assert result["toolCallId"] == "call_1"
        assert "VALID" in result["result"]

    def test_invalid_value_asks_reprompt(self, client):
        resp = _tool_call(client, "validate_patient_field", {"field": "phone_number", "value": "123"})
        assert "INVALID" in resp.json()["results"][0]["result"]


class TestRegisterTool:
    def test_happy_path_persists_patient(self, client, db_session):
        resp = _tool_call(client, "register_patient", REGISTRATION_ARGS)
        result = resp.json()["results"][0]["result"]
        assert "SUCCESS" in result and "You're all set, Maria" in result

        patient = db_session.scalars(select(Patient)).one()
        assert patient.last_name == "Garcia"
        assert patient.phone_number == "3055550142"

    def test_validation_failure_lists_fields(self, client, db_session):
        bad = dict(REGISTRATION_ARGS, date_of_birth="12/31/2999", zip_code="1")
        resp = _tool_call(client, "register_patient", bad)
        result = resp.json()["results"][0]["result"]
        assert "VALIDATION FAILED" in result
        assert "date_of_birth" in result and "zip_code" in result
        assert db_session.scalars(select(Patient)).first() is None

    def test_duplicate_phone_detected(self, client):
        _tool_call(client, "register_patient", REGISTRATION_ARGS)
        resp = _tool_call(client, "register_patient", dict(REGISTRATION_ARGS, first_name="Marco"))
        result = resp.json()["results"][0]["result"]
        assert "DUPLICATE PHONE NUMBER" in result and "Maria Garcia" in result

    def test_duplicate_override(self, client, db_session):
        _tool_call(client, "register_patient", REGISTRATION_ARGS)
        resp = _tool_call(
            client, "register_patient",
            dict(REGISTRATION_ARGS, first_name="Marco", allow_duplicate=True),
        )
        assert "SUCCESS" in resp.json()["results"][0]["result"]
        assert len(db_session.scalars(select(Patient)).all()) == 2


class TestLookupAndUpdateTools:
    def test_lookup_not_found(self, client):
        resp = _tool_call(client, "lookup_patient_by_phone", {"phone_number": "3055550000"})
        assert "No existing patient" in resp.json()["results"][0]["result"]

    def test_lookup_found_then_update(self, client, db_session):
        _tool_call(client, "register_patient", REGISTRATION_ARGS)
        resp = _tool_call(client, "lookup_patient_by_phone", {"phone_number": "(305) 555-0142"})
        result = resp.json()["results"][0]["result"]
        assert "EXISTING PATIENT FOUND" in result
        patient_id = result.split("patient_id=")[1].split(".")[0]

        resp = _tool_call(client, "update_patient", {"patient_id": patient_id, "city": "Tampa"})
        assert "SUCCESS" in resp.json()["results"][0]["result"]
        patient = db_session.scalars(select(Patient)).one()
        assert patient.city == "Tampa"

    def test_update_bad_uuid(self, client):
        resp = _tool_call(client, "update_patient", {"patient_id": "nope", "city": "Tampa"})
        assert "INVALID patient_id" in resp.json()["results"][0]["result"]


class TestScheduleTool:
    def test_mock_booking(self, client):
        resp = _tool_call(
            client, "schedule_appointment",
            {"patient_id": "any", "preferred_day": "Friday", "preferred_time": "morning"},
        )
        result = resp.json()["results"][0]["result"]
        assert "APPOINTMENT BOOKED" in result and "APT-" in result


class TestEndOfCallReport:
    def test_persists_call_log_and_links_patient(self, client, db_session):
        _tool_call(client, "register_patient", REGISTRATION_ARGS)
        payload = {
            "message": {
                "type": "end-of-call-report",
                "endedReason": "assistant-ended-call",
                "transcript": "AI: Thank you for calling CareCloud...\nUser: Hi...",
                "call": {"id": "vapi-call-123", "customer": {"number": "+13055550142"}},
                "analysis": {
                    "summary": "Caller Maria Garcia registered as a new patient.",
                    "structuredData": {
                        "first_name": "Maria",
                        "phone_number": "3055550142",
                        "registration_completed": True,
                    },
                },
                "startedAt": "2026-09-23T19:00:00Z",
                "endedAt": "2026-09-23T19:04:30Z",
            }
        }
        resp = client.post("/vapi/webhook", json=payload, headers=HEADERS)
        assert resp.status_code == 200

        log = db_session.scalars(select(CallLog)).one()
        patient = db_session.scalars(select(Patient)).one()
        assert log.vapi_call_id == "vapi-call-123"
        assert log.patient_id == patient.patient_id
        assert log.status == "completed"
        assert "CareCloud" in log.transcript

    def test_dropped_call_marked_incomplete(self, client, db_session):
        payload = {
            "message": {
                "type": "end-of-call-report",
                "endedReason": "customer-ended-call",
                "transcript": "AI: Could I start with your first name?\nUser: John—",
                "call": {"id": "vapi-call-456", "customer": {"number": "+13055559999"}},
                "analysis": {"structuredData": {"first_name": "John"}},
            }
        }
        client.post("/vapi/webhook", json=payload, headers=HEADERS)
        log = db_session.scalars(select(CallLog)).one()
        assert log.status == "incomplete"
        assert log.structured_data == {"first_name": "John"}
