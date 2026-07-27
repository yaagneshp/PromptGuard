from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session

from . import crud, models
from .auth import require_api_key
from .config import settings
from .database import Base, engine, get_db
from .detectors import scan_text_combined
from .detectors.presidio_detector import get_analyzer
from .ratelimit import limiter
from .risk import score_from_matches
from .schemas import ComplianceTagOut, DetectionOut, EventOut, IngestRequest, RiskScoreOut

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Loading the spaCy model takes a few seconds; do it once at startup
    # rather than on the first request.
    get_analyzer()
    yield


app = FastAPI(title="PromptGuard API", version="0.1.0", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Basic hardening headers. Low-priority for a pure JSON API (no HTML is ever
# served) but cheap and standard practice.
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


# The Chrome extension's background service worker fetch bypasses page-level
# CORS entirely (MV3 background workers with host_permissions aren't subject
# to it), so this middleware only gates browser-context requests - e.g. a web
# page's own JS calling the API directly. No origins are allowed by default;
# set ALLOWED_ORIGINS in .env (comma-separated) if you need that.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


def _event_to_out(event: models.Event) -> EventOut:
    return EventOut(
        id=event.id,
        external_user_id=event.user.external_user_id,
        platform=event.platform.name,
        redacted_text=event.redacted_text,
        char_count=event.char_count,
        occurred_at=event.occurred_at,
        received_at=event.received_at,
        detections=[DetectionOut.model_validate(d) for d in event.detections],
        risk_score=RiskScoreOut.model_validate(event.risk_score),
        compliance_tags=[ComplianceTagOut.model_validate(t) for t in event.compliance_tags],
    )


@app.post("/events/ingest", response_model=EventOut, dependencies=[Depends(require_api_key)])
@limiter.limit("30/minute")
def ingest_event(request: Request, payload: IngestRequest, db: Session = Depends(get_db)) -> EventOut:
    scan = scan_text_combined(payload.text)
    risk = score_from_matches(scan.matches, payload.text)

    event = crud.create_event_with_scan(
        db,
        external_user_id=payload.external_user_id,
        platform_name=payload.platform,
        occurred_at=payload.occurred_at,
        raw_text=payload.text,
        scan=scan,
        risk=risk,
    )
    return _event_to_out(event)


@app.get("/events", response_model=list[EventOut], dependencies=[Depends(require_api_key)])
@limiter.limit("60/minute")
def get_events(request: Request, limit: int = 50, db: Session = Depends(get_db)) -> list[EventOut]:
    events = crud.list_events(db, limit=limit)
    return [_event_to_out(e) for e in events]
