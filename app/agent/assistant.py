"""Builds the complete Vapi assistant payload from the prompt + tool schemas.

Used by scripts/setup_vapi.py to create or update the assistant, so the
assistant configuration is version-controlled alongside the code.
"""

import re
from pathlib import Path

from app.agent.tools import build_tools

ASSISTANT_NAME = "CareCloud Patient Registration"

_PROMPT_PATH = Path(__file__).parent / "system_prompt.md"


def load_system_prompt() -> str:
    """Read system_prompt.md and strip the HTML design-note comments."""
    text = _PROMPT_PATH.read_text(encoding="utf-8")
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip()


# Structured-data schema used by Vapi's post-call analysis. Even if a call
# drops before registration, Vapi extracts whatever demographics were spoken
# and we persist them in call_logs.structured_data.
STRUCTURED_DATA_SCHEMA = {
    "type": "object",
    "properties": {
        "first_name": {"type": "string"},
        "last_name": {"type": "string"},
        "date_of_birth": {"type": "string"},
        "sex": {"type": "string"},
        "phone_number": {"type": "string"},
        "email": {"type": "string"},
        "address_line_1": {"type": "string"},
        "address_line_2": {"type": "string"},
        "city": {"type": "string"},
        "state": {"type": "string"},
        "zip_code": {"type": "string"},
        "insurance_provider": {"type": "string"},
        "insurance_member_id": {"type": "string"},
        "preferred_language": {"type": "string"},
        "emergency_contact_name": {"type": "string"},
        "emergency_contact_phone": {"type": "string"},
        "registration_completed": {
            "type": "boolean",
            "description": "True if the agent confirmed the record was saved successfully.",
        },
    },
}


def build_assistant(public_base_url: str, webhook_secret: str) -> dict:
    webhook_url = f"{public_base_url.rstrip('/')}/vapi/webhook"

    return {
        "name": ASSISTANT_NAME,
        "firstMessage": (
            "Thank you for calling CareCloud! This is Riley. "
            "I can get you registered as a new patient in just a couple of minutes. "
            "Could I start with your first name?"
        ),
        "model": {
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 0.4,
            "messages": [{"role": "system", "content": load_system_prompt()}],
            "tools": build_tools(webhook_url, webhook_secret),
        },
        "voice": {
            "provider": "vapi",
            "voiceId": "Emma",  # V2 voice: natural female American voice
            "version": 2,
            "language": "auto",  # auto-detects language -> speaks Spanish for the bonus flow
        },
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-3",
            # "multi" lets Deepgram follow a mid-call switch to Spanish (bonus).
            "language": "multi",
        },
        # Server messages -> app/routers/vapi.py
        "server": {"url": webhook_url, "secret": webhook_secret},
        "serverMessages": ["tool-calls", "end-of-call-report", "status-update"],
        # Let the model end the call after the goodbye.
        "endCallFunctionEnabled": True,
        "endCallMessage": "Thanks for calling CareCloud. Take care!",
        # Resilience knobs.
        "silenceTimeoutSeconds": 30,
        "maxDurationSeconds": 900,
        # Post-call analysis feeds call_logs (transcript/summary/structured data).
        "analysisPlan": {
            "summaryPlan": {"enabled": True},
            "structuredDataPlan": {
                "enabled": True,
                "schema": STRUCTURED_DATA_SCHEMA,
            },
        },
    }
