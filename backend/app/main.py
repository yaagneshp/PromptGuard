from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import crud, models
from .auth import require_api_key
from .config import settings
from .database import Base, engine, get_db
from .detectors import scan_text_combined
from .detectors.presidio_detector import get_analyzer
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
def ingest_event(payload: IngestRequest, db: Session = Depends(get_db)) -> EventOut:
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
def get_events(limit: int = 50, db: Session = Depends(get_db)) -> list[EventOut]:
    events = crud.list_events(db, limit=limit)
    return [_event_to_out(e) for e in events]
