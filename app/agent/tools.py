"""Vapi tool definitions - the single source of truth for the agent's tools.

Each tool is a Vapi "function" tool whose calls are POSTed to
``{PUBLIC_BASE_URL}/vapi/webhook`` and handled in app/routers/vapi.py.
"""

_PATIENT_PROPERTIES = {
    "first_name": {"type": "string", "description": "Legal first name."},
    "last_name": {"type": "string", "description": "Legal last name."},
    "date_of_birth": {"type": "string", "description": "Date of birth, MM/DD/YYYY."},
    "sex": {
        "type": "string",
        "enum": ["Male", "Female", "Other", "Decline to Answer"],
        "description": "Sex as stated by the caller.",
    },
    "phone_number": {"type": "string", "description": "10-digit US phone number."},
    "email": {"type": "string", "description": "Email address (optional)."},
    "address_line_1": {"type": "string", "description": "Street address line 1."},
    "address_line_2": {"type": "string", "description": "Apt/Suite/Unit (optional)."},
    "city": {"type": "string", "description": "City."},
    "state": {"type": "string", "description": "2-letter US state abbreviation."},
    "zip_code": {"type": "string", "description": "5-digit or ZIP+4."},
    "insurance_provider": {"type": "string", "description": "Insurance company name (optional)."},
    "insurance_member_id": {"type": "string", "description": "Insurance member ID (optional)."},
    "preferred_language": {"type": "string", "description": "Preferred language, default English."},
    "emergency_contact_name": {"type": "string", "description": "Emergency contact full name (optional)."},
    "emergency_contact_phone": {"type": "string", "description": "Emergency contact 10-digit phone (optional)."},
}

_REQUIRED_FIELDS = [
    "first_name", "last_name", "date_of_birth", "sex", "phone_number",
    "address_line_1", "city", "state", "zip_code",
]


def build_tools(server_url: str, secret: str) -> list[dict]:
    server = {"url": server_url}
    if secret:
        server["secret"] = secret

    return [
        {
            "type": "function",
            "async": False,
            "server": server,
            "function": {
                "name": "validate_patient_field",
                "description": (
                    "Validate a single demographic field the caller just provided "
                    "(date_of_birth, phone_number, zip_code, state, email, etc). "
                    "Returns VALID with a normalized value, or INVALID with the reason "
                    "so you can re-ask for exactly that field."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "field": {
                            "type": "string",
                            "enum": list(_PATIENT_PROPERTIES.keys()),
                            "description": "Which field to validate.",
                        },
                        "value": {"type": "string", "description": "The value as heard from the caller."},
                    },
                    "required": ["field", "value"],
                },
            },
        },
        {
            "type": "function",
            "async": False,
            "server": server,
            "function": {
                "name": "lookup_patient_by_phone",
                "description": (
                    "Check whether a patient already exists with this phone number. "
                    "Call this once, right after the caller's phone number is validated, "
                    "to detect returning patients."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone_number": {"type": "string", "description": "10-digit US phone number."}
                    },
                    "required": ["phone_number"],
                },
            },
        },
        {
            "type": "function",
            "async": False,
            "server": server,
            "function": {
                "name": "register_patient",
                "description": (
                    "Save the new patient record to the database. Call ONLY after reading "
                    "all information back to the caller and receiving an explicit yes. "
                    "Returns SUCCESS, or VALIDATION FAILED / DUPLICATE / DATABASE ERROR "
                    "with instructions on what to do next."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        **_PATIENT_PROPERTIES,
                        "allow_duplicate": {
                            "type": "boolean",
                            "description": (
                                "Set true only if the caller confirmed they want a new record "
                                "despite an existing patient having the same phone number."
                            ),
                        },
                    },
                    "required": _REQUIRED_FIELDS,
                },
            },
        },
        {
            "type": "function",
            "async": False,
            "server": server,
            "function": {
                "name": "update_patient",
                "description": (
                    "Update fields on an existing patient record (returning caller flow). "
                    "Requires the patient_id from lookup_patient_by_phone. Only send the "
                    "fields the caller wants to change, after confirming them."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "patient_id": {"type": "string", "description": "UUID from lookup_patient_by_phone."},
                        **_PATIENT_PROPERTIES,
                    },
                    "required": ["patient_id"],
                },
            },
        },
        {
            "type": "function",
            "async": False,
            "server": server,
            "function": {
                "name": "schedule_appointment",
                "description": (
                    "Book a (mock) first appointment for a registered patient. Offer this "
                    "after a successful registration. Read the returned date, time, and "
                    "confirmation code back to the caller."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "patient_id": {"type": "string", "description": "UUID of the registered patient."},
                        "preferred_day": {"type": "string", "description": "Caller's preferred day."},
                        "preferred_time": {"type": "string", "description": "Caller's preferred time of day."},
                    },
                    "required": ["patient_id"],
                },
            },
        },
    ]
