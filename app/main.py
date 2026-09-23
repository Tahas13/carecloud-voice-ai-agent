"""CareCloud Voice AI - Patient Registration service.

FastAPI app wiring: routers, response-envelope exception handlers, startup
table creation, and optional demo seeding.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.schemas import error_body

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("carecloud")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Simple create_all is intentional for a 3-hour take-home; a production
    # system would use Alembic migrations (documented in README trade-offs).
    Base.metadata.create_all(bind=engine)
    if settings.seed_demo_data:
        from app.seed import seed_if_empty

        with SessionLocal() as db:
            seed_if_empty(db)
    yield


app = FastAPI(
    title="CareCloud Voice AI - Patient Registration",
    description="Voice AI agent + REST API for patient registration (take-home assessment).",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Envelope exception handlers: every error is {"data": null, "error": {...}}
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = [
        {"field": ".".join(str(p) for p in err["loc"] if p != "body"), "message": err["msg"]}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=error_body("validation_error", "Request validation failed.", details),
    )


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    codes = {400: "bad_request", 404: "not_found", 422: "validation_error", 401: "unauthorized"}
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(codes.get(exc.status_code, "error"), str(exc.detail)),
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=error_body("internal_error", "An unexpected error occurred."),
    )


# Routers are imported after app creation to keep import order simple.
from app.routers import dashboard, health, patients, vapi  # noqa: E402

app.include_router(health.router)
app.include_router(patients.router)
app.include_router(vapi.router)
app.include_router(dashboard.router)


@app.get("/")
def root():
    from app.schemas import envelope

    return envelope(
        {
            "service": "CareCloud Voice AI - Patient Registration",
            "endpoints": ["/health", "/patients", "/dashboard", "/docs"],
        }
    )
