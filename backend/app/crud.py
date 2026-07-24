import datetime
import hashlib

from sqlalchemy.orm import Session

from . import models
from .detectors import ScanResult
from .risk import RiskResult


def get_or_create_user(db: Session, external_user_id: str) -> models.User:
    user = db.query(models.User).filter_by(external_user_id=external_user_id).first()
    if user is None:
        user = models.User(external_user_id=external_user_id)
        db.add(user)
        db.flush()
    return user


def get_or_create_platform(db: Session, name: str) -> models.Platform:
    key = name.strip().lower()
    platform = db.query(models.Platform).filter_by(name=key).first()
    if platform is None:
        platform = models.Platform(name=key, display_name=name.strip())
        db.add(platform)
        db.flush()
    return platform


def hash_raw_text(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def create_event_with_scan(
    db: Session,
    *,
    external_user_id: str,
    platform_name: str,
    occurred_at: datetime.datetime | None,
    raw_text: str,
    scan: ScanResult,
    risk: RiskResult,
) -> models.Event:
    user = get_or_create_user(db, external_user_id)
    platform = get_or_create_platform(db, platform_name)

    event = models.Event(
        user_id=user.id,
        platform_id=platform.id,
        redacted_text=scan.redacted_text,
        char_count=scan.raw_char_count,
        raw_text_hash=hash_raw_text(raw_text),
        occurred_at=occurred_at or models.utcnow(),
    )
    db.add(event)
    db.flush()

    for category, count in scan.category_counts.items():
        db.add(
            models.Detection(
                event_id=event.id,
                category=category,
                match_count=count,
                detector_source="regex",
            )
        )

    db.add(
        models.RiskScore(
            event_id=event.id,
            regex_score=risk.regex_score,
            combined_score=risk.combined_score,
            risk_level=risk.risk_level,
        )
    )

    db.commit()
    db.refresh(event)
    return event


def list_events(db: Session, limit: int = 50) -> list[models.Event]:
    return (
        db.query(models.Event)
        .order_by(models.Event.received_at.desc())
        .limit(limit)
        .all()
    )
