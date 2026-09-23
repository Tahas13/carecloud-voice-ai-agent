"""Field validation and normalization, single-sourced.

Both the REST API (via Pydantic schemas) and the voice agent's
``validate_patient_field`` tool call into these functions, so the exact same
rules apply no matter where data enters the system.

Each ``validate_*`` function returns the normalized value, or raises
``ValueError`` with a human/LLM-friendly message describing what's wrong.
"""

import re
from datetime import date, datetime

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z' \-]{0,49}$")
ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SEX_VALUES = ("Male", "Female", "Other", "Decline to Answer")

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}
_STATE_NAME_TO_ABBREV = {name.lower(): abbrev for abbrev, name in US_STATES.items()}


def validate_name(value: str, field: str = "name") -> str:
    value = " ".join(str(value).split())  # collapse whitespace
    if not value:
        raise ValueError(f"{field} is required.")
    if not NAME_RE.match(value):
        raise ValueError(
            f"{field} must be 1-50 characters using letters, hyphens, or apostrophes."
        )
    return value


def validate_dob(value) -> date:
    """Accept MM/DD/YYYY (spec format) or ISO YYYY-MM-DD. Must be in the past."""
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        text = str(value).strip()
        parsed = None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
            try:
                parsed = datetime.strptime(text, fmt).date()
                break
            except ValueError:
                continue
        if parsed is None:
            raise ValueError("date_of_birth must be a valid date in MM/DD/YYYY format.")
    today = date.today()
    if parsed > today:
        raise ValueError("date_of_birth cannot be in the future.")
    if parsed.year < today.year - 120:
        raise ValueError("date_of_birth is more than 120 years ago; please double-check it.")
    return parsed


def validate_phone(value: str, field: str = "phone_number") -> str:
    """Normalize to exactly 10 digits (strip formatting and a leading US '1')."""
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError(f"{field} must be a valid 10-digit U.S. phone number.")
    if digits[0] in "01":
        raise ValueError(f"{field} area code cannot start with 0 or 1.")
    return digits


def validate_sex(value: str) -> str:
    text = str(value).strip().lower()
    aliases = {
        "male": "Male", "m": "Male", "man": "Male",
        "female": "Female", "f": "Female", "woman": "Female",
        "other": "Other", "non-binary": "Other", "nonbinary": "Other",
        "decline": "Decline to Answer", "decline to answer": "Decline to Answer",
        "prefer not to say": "Decline to Answer", "prefer not to answer": "Decline to Answer",
    }
    if text in aliases:
        return aliases[text]
    raise ValueError(f"sex must be one of: {', '.join(SEX_VALUES)}.")


def validate_state(value: str) -> str:
    text = str(value).strip()
    if len(text) == 2 and text.upper() in US_STATES:
        return text.upper()
    abbrev = _STATE_NAME_TO_ABBREV.get(text.lower())
    if abbrev:
        return abbrev
    raise ValueError("state must be a valid 2-letter U.S. state abbreviation (e.g. NY, CA).")


def validate_zip(value: str) -> str:
    text = str(value).strip().replace(" ", "")
    if not ZIP_RE.match(text):
        raise ValueError("zip_code must be a 5-digit or ZIP+4 U.S. format (e.g. 33301 or 33301-1234).")
    return text


def validate_email(value: str) -> str:
    text = str(value).strip().lower()
    if not EMAIL_RE.match(text):
        raise ValueError("email is not a valid email address.")
    return text


def validate_city(value: str) -> str:
    text = " ".join(str(value).split())
    if not (1 <= len(text) <= 100):
        raise ValueError("city must be 1-100 characters.")
    return text


def validate_free_text(value: str, field: str, max_len: int = 200) -> str:
    """Basic sanitization for free-text fields (addresses, insurance names)."""
    text = " ".join(str(value).split())
    # Strip characters that have no business in demographic text fields.
    text = re.sub(r"[<>{};`]", "", text)
    if not (1 <= len(text) <= max_len):
        raise ValueError(f"{field} must be 1-{max_len} characters.")
    return text


# Map used by the voice agent's validate_patient_field tool. Each entry
# validates a single field as it is captured mid-conversation.
FIELD_VALIDATORS = {
    "first_name": lambda v: validate_name(v, "first_name"),
    "last_name": lambda v: validate_name(v, "last_name"),
    "date_of_birth": lambda v: validate_dob(v).strftime("%m/%d/%Y"),
    "sex": validate_sex,
    "phone_number": lambda v: validate_phone(v, "phone_number"),
    "email": validate_email,
    "address_line_1": lambda v: validate_free_text(v, "address_line_1"),
    "address_line_2": lambda v: validate_free_text(v, "address_line_2"),
    "city": validate_city,
    "state": validate_state,
    "zip_code": validate_zip,
    "insurance_provider": lambda v: validate_free_text(v, "insurance_provider", 100),
    "insurance_member_id": lambda v: validate_free_text(v, "insurance_member_id", 50),
    "preferred_language": lambda v: validate_free_text(v, "preferred_language", 50),
    "emergency_contact_name": lambda v: validate_name(v, "emergency_contact_name"),
    "emergency_contact_phone": lambda v: validate_phone(v, "emergency_contact_phone"),
}
