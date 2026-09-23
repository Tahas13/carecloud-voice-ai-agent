"""Optional seed data: two fake demonstration patients (assessment section 3).

Only runs when the patients table is empty, so it never clobbers real data.
All data here is fictional.
"""

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Patient

logger = logging.getLogger("carecloud.seed")

SEED_PATIENTS = [
    dict(
        first_name="Jane",
        last_name="Doe",
        date_of_birth=date(1985, 4, 12),
        sex="Female",
        phone_number="5551234567",
        email="jane.doe@example.com",
        address_line_1="123 Maple Street",
        address_line_2="Apt 4B",
        city="Miami",
        state="FL",
        zip_code="33101",
        insurance_provider="Blue Cross Blue Shield",
        insurance_member_id="BCBS123456",
        preferred_language="English",
        emergency_contact_name="John Doe",
        emergency_contact_phone="5557654321",
    ),
    dict(
        first_name="Carlos",
        last_name="Rivera",
        date_of_birth=date(1972, 11, 3),
        sex="Male",
        phone_number="5559876543",
        address_line_1="456 Ocean Drive",
        city="Fort Lauderdale",
        state="FL",
        zip_code="33301-2200",
        preferred_language="Spanish",
    ),
]


def seed_if_empty(db: Session) -> None:
    if db.scalars(select(Patient).limit(1)).first() is not None:
        return
    for record in SEED_PATIENTS:
        db.add(Patient(**record))
    db.commit()
    logger.info("Seeded %d demo patients.", len(SEED_PATIENTS))
