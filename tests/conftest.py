"""Test fixtures: in-memory SQLite database + FastAPI TestClient.

Environment is pinned BEFORE the app is imported so the cached settings pick
up test values (webhook secret, no demo seeding).
"""

import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["VAPI_WEBHOOK_SECRET"] = "test-secret"
os.environ["SEED_DEMO_DATA"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    yield db
    db.close()


VALID_PATIENT = {
    "first_name": "Maria",
    "last_name": "Garcia",
    "date_of_birth": "04/12/1985",
    "sex": "Female",
    "phone_number": "(305) 555-0142",
    "email": "maria.garcia@example.com",
    "address_line_1": "789 Palm Ave",
    "city": "Miami",
    "state": "Florida",
    "zip_code": "33101",
}


@pytest.fixture
def valid_patient():
    return dict(VALID_PATIENT)
