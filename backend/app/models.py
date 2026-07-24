import datetime

from sqlalchemy import ForeignKey, String, Text, Integer, Float, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class User(Base):
    """A data subject being monitored (an org employee), not a login account."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    external_user_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    events: Mapped[list["Event"]] = relationship(back_populates="user")


class Platform(Base):
    __tablename__ = "platforms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    events: Mapped[list["Event"]] = relationship(back_populates="platform")


class Event(Base):
    """
    A single captured prompt-submission telemetry event.

    Only the redacted version of the prompt is ever persisted. `raw_text_hash`
    is a SHA-256 digest of the original text, kept for audit/dedup purposes —
    it cannot be reversed back into the original content.
    """

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id"), index=True)

    event_type: Mapped[str] = mapped_column(String(32), default="prompt_submission")
    redacted_text: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer)
    raw_text_hash: Mapped[str] = mapped_column(String(64))

    occurred_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="events")
    platform: Mapped["Platform"] = relationship(back_populates="events")
    detections: Mapped[list["Detection"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    risk_score: Mapped["RiskScore"] = relationship(
        back_populates="event", uselist=False, cascade="all, delete-orphan"
    )


class Detection(Base):
    """One PII category match found within an event (counts only, no raw matched text)."""

    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)

    category: Mapped[str] = mapped_column(String(64))
    match_count: Mapped[int] = mapped_column(Integer, default=0)
    detector_source: Mapped[str] = mapped_column(String(32), default="regex")

    event: Mapped["Event"] = relationship(back_populates="detections")


class RiskScore(Base):
    __tablename__ = "risk_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), unique=True, index=True)

    regex_score: Mapped[float] = mapped_column(Float, default=0.0)
    presidio_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    contextual_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    combined_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(16), default="low")

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    event: Mapped["Event"] = relationship(back_populates="risk_score")


__all__ = ["User", "Platform", "Event", "Detection", "RiskScore"]
