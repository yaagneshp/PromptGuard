from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import crud, models
from .auth import require_api_key
from .database import Base, engine, get_db
from .detectors import scan_text
from .risk import score_from_counts
from .schemas import DetectionOut, EventOut, IngestRequest, RiskScoreOut

Base.metadata.create_all(bind=engine)

app = FastAPI(title="PromptGuard API", version="0.1.0")

# Chrome extension background service workers fetch this API directly from a
# chrome-extension:// origin, which is cross-origin as far as CORS is
# concerned. Wide open for MVP/local-demo purposes; tighten allow_origins to
# the specific chrome-extension://<id> before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    )


@app.post("/events/ingest", response_model=EventOut, dependencies=[Depends(require_api_key)])
def ingest_event(payload: IngestRequest, db: Session = Depends(get_db)) -> EventOut:
    scan = scan_text(payload.text)
    risk = score_from_counts(scan.category_counts)

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
