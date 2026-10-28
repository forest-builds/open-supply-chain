from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RiskScoreRequest(BaseModel):
    lat: float
    lon: float
    radius_km: float = 50.0
    incident_types: list[str] = []


class RiskScoreResponse(BaseModel):
    score: float  # 0-100
    level: str  # low, moderate, high, critical
    factors: dict[str, float]
    assessed_at: str


class SitrepRequest(BaseModel):
    incident_id: str
    include_resources: bool = True
    include_weather: bool = True


class SitrepResponse(BaseModel):
    incident_id: str
    summary: str
    situation: str
    current_conditions: str
    resource_status: str | None
    weather_impact: str | None
    generated_at: str


class OperationalCheckRequest(BaseModel):
    location: str
    operation_type: str = "field_dispatch"
    time_window: str = "next_4_hours"
    risk_tolerance: str = "normal"


class OperationalCheckResponse(BaseModel):
    decision: str
    score: int
    level: str
    confidence: str
    coverage_level: str
    safe_for_automation: str
    action: str
    reason: str
    location: str
    operation_type: str
    time_window: str
    risk_tolerance: str
    included_sources: list[str]
    excluded_sources: list[str]
    coverage_warning: str
    brief_id: str | None = None
    computed_at: datetime


class DecisionEvaluateRequest(BaseModel):
    subject: str = "demo"
    intent: str = "evaluate"
    context: dict[str, Any] = Field(default_factory=dict)


class DecisionEvaluateResponse(BaseModel):
    status: str
    recommendation: str
    rationale: str
    evaluated_at: datetime
