"""Idempotently configure Vapi from the version-controlled assistant definition.

Usage (after deploying the API and setting env vars / .env):

    python scripts/setup_vapi.py

What it does:
1. Creates the assistant, or updates it if one with the same name exists.
2. Attaches the assistant to your Vapi phone number (creates a free US number
   if the account has none).
3. Prints the phone number to call.

Requires: VAPI_API_KEY, PUBLIC_BASE_URL, VAPI_WEBHOOK_SECRET.
"""

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.assistant import ASSISTANT_NAME, build_assistant  # noqa: E402
from app.config import get_settings  # noqa: E402

BASE = "https://api.vapi.ai"


def main() -> None:
    settings = get_settings()
    if not settings.vapi_api_key:
        sys.exit("VAPI_API_KEY is not set (see .env.example).")
    if not settings.public_base_url or "localhost" in settings.public_base_url:
        print(
            "WARNING: PUBLIC_BASE_URL looks local. Vapi must be able to reach it "
            "over HTTPS (deploy first, or use an ngrok URL)."
        )

    headers = {"Authorization": f"Bearer {settings.vapi_api_key}"}
    payload = build_assistant(settings.public_base_url, settings.vapi_webhook_secret)

    # --- 1. Create or update the assistant (match by name) -------------------
    resp = requests.get(f"{BASE}/assistant", headers=headers, timeout=30)
    resp.raise_for_status()
    existing = next((a for a in resp.json() if a.get("name") == ASSISTANT_NAME), None)

    if existing:
        assistant_id = existing["id"]
        resp = requests.patch(
            f"{BASE}/assistant/{assistant_id}", headers=headers, json=payload, timeout=30
        )
        action = "Updated"
    else:
        resp = requests.post(f"{BASE}/assistant", headers=headers, json=payload, timeout=30)
        action = "Created"
    if not resp.ok:
        sys.exit(f"Vapi assistant {action.lower()} failed ({resp.status_code}): {resp.text}")
    assistant_id = resp.json()["id"]
    print(f"{action} assistant '{ASSISTANT_NAME}' ({assistant_id})")

    # --- 2. Ensure a phone number exists and points at the assistant ---------
    resp = requests.get(f"{BASE}/phone-number", headers=headers, timeout=30)
    resp.raise_for_status()
    numbers = resp.json()

    if not numbers:
        print("No phone number on the account; creating a free Vapi US number...")
        resp = None
        for area_code in ("708", "463", "945", "415", "212", "305"):
            resp = requests.post(
                f"{BASE}/phone-number",
                headers=headers,
                json={
                    "provider": "vapi",
                    "assistantId": assistant_id,
                    "numberDesiredAreaCode": area_code,
                },
                timeout=60,
            )
            if resp.ok:
                break
            print(f"  area code {area_code} unavailable ({resp.status_code}), trying next...")
        if resp is None or not resp.ok:
            sys.exit(
                f"Could not create a phone number ({resp.status_code}): {resp.text}\n"
                "Create one manually: dashboard.vapi.ai -> Phone Numbers -> Create -> Free Vapi Number,"
                " then re-run this script."
            )
        numbers = [resp.json()]

    number = numbers[0]
    resp = requests.patch(
        f"{BASE}/phone-number/{number['id']}",
        headers=headers,
        json={"assistantId": assistant_id},
        timeout=30,
    )
    if not resp.ok:
        sys.exit(f"Could not attach assistant to number ({resp.status_code}): {resp.text}")
    number = resp.json()

    print()
    print("=" * 60)
    print(f"  Call this number: {number.get('number', '(see Vapi dashboard)')}")
    print(f"  Webhook: {settings.public_base_url.rstrip('/')}/vapi/webhook")
    print("=" * 60)


if __name__ == "__main__":
    main()
