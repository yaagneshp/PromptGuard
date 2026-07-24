import datetime
import hashlib

from sqlalchemy.orm import Session

from . import gdpr, models
from .detectors.combined import CombinedScanResult
from .policy import policy
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
    scan: CombinedScanResult,
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

    category_counts: dict[str, tuple[int, str]] = {}
    for m in scan.matches:
        count, _ = category_counts.get(m.category, (0, m.source))
        category_counts[m.category] = (count + 1, m.source)

    for category, (count, source) in category_counts.items():
        db.add(
            models.Detection(
                event_id=event.id,
                category=category,
                match_count=count,
                detector_source=source,
            )
        )

    categories_present = set(category_counts.keys())
    policy_violation = bool(policy.blocked_categories_present(categories_present)) or not policy.is_platform_allowed(
        platform_name
    )

    db.add(
        models.RiskScore(
            event_id=event.id,
            regex_score=risk.regex_score,
            presidio_score=risk.presidio_score,
            contextual_score=risk.contextual_score,
            combined_score=risk.combined_score,
            risk_level=risk.risk_level,
            policy_violation=policy_violation,
        )
    )

    for category, article, rationale in gdpr.tags_for_categories(categories_present):
        db.add(
            models.ComplianceTag(
                event_id=event.id,
                category=category,
                gdpr_article=article,
                rationale=rationale,
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
