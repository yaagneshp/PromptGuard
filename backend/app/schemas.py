import datetime

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    external_user_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Pseudonymous ID for the person submitting the prompt",
    )
    platform: str = Field(
        ...,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Platform key, e.g. 'chatgpt', 'claude', 'gemini'",
    )
    # 50k chars bounds worst-case Presidio/spaCy processing cost per request;
    # generous enough for any realistic single prompt submission.
    text: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="Raw prompt text — scanned in-memory, never persisted as-is",
    )
    occurred_at: datetime.datetime | None = Field(
        default=None, description="Client-side timestamp of submission; defaults to server receive time"
    )


class DetectionOut(BaseModel):
    category: str
    match_count: int
    detector_source: str

    model_config = {"from_attributes": True}


class RiskScoreOut(BaseModel):
    regex_score: float
    presidio_score: float | None
    contextual_score: float | None
    combined_score: float
    risk_level: str
    policy_violation: bool

    model_config = {"from_attributes": True}


class ComplianceTagOut(BaseModel):
    category: str
    gdpr_article: str
    rationale: str

    model_config = {"from_attributes": True}


class EventOut(BaseModel):
    id: int
    external_user_id: str
    platform: str
    redacted_text: str
    char_count: int
    occurred_at: datetime.datetime
    received_at: datetime.datetime
    detections: list[DetectionOut]
    risk_score: RiskScoreOut
    compliance_tags: list[ComplianceTagOut]

    model_config = {"from_attributes": True}
