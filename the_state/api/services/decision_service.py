from datetime import datetime, timezone

from ingestion.nyc import NYC_DATASETS
from schemas.decision import (
    DecisionEvaluateRequest,
    DecisionEvaluateResponse,
    OperationalCheckRequest,
    OperationalCheckResponse,
    RiskScoreRequest,
    RiskScoreResponse,
    SitrepRequest,
    SitrepResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession
from state_products.location_state.decision import decide

from services.location_state_service import LocationStateService

# Friendly source ids for the public records we actually pull today.
_SOURCE_LABEL = {
    "311": "nyc_311",
    "dot_street_closures": "nyc_dot_street_closures",
    "nyc_events": "nyc_permitted_events",
    "hpd_violations": "building_housing_violations",
    "hpd_complaints": "building_housing_complaints",
    "nypd_collisions": "nyc_vehicle_collisions",
    "film_permits": "nyc_film_permits",
    "dob_permits": "nyc_construction_permits",
}
INCLUDED_SOURCES = sorted(_SOURCE_LABEL.get(k, k) for k in NYC_DATASETS)
# Explicitly NOT connected yet - shown so the coverage is honest.
EXCLUDED_SOURCES = [
    "weather_alerts",
    "live_traffic",
    "transit_status",
    "emergency_alerts",
]
_COVERAGE_WARNING = (
    "This decision is based only on currently connected public records "
    "(NYC). Sources not yet connected are excluded, not assumed safe."
)

# Friendly time windows -> the engine's internal window grammar.
_WINDOW_MAP = {
    "next_1_hour": "1h",
    "next_4_hours": "4h",
    "next_8_hours": "8h",
    "next_12_hours": "12h",
    "next_24_hours": "24h",
    "next_3_days": "3d",
    "next_7_days": "7d",
}


def _internal_window(value: str) -> str:
    return _WINDOW_MAP.get(value, value if value else "24h")


class DecisionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def score_risk(self, req: RiskScoreRequest) -> RiskScoreResponse:
        # TODO: implement actual scoring via state_engine + ingestion data
        return RiskScoreResponse(
            score=0.0,
            level="low",
            factors={},
            assessed_at=datetime.now(timezone.utc).isoformat(),
        )

    async def generate_sitrep(self, req: SitrepRequest) -> SitrepResponse:
        # TODO: implement sitrep generation via decision_apis.incident_sitrep
        return SitrepResponse(
            incident_id=req.incident_id,
            summary="Situation report generation not yet implemented.",
            situation="",
            current_conditions="",
            resource_status=None,
            weather_impact=None,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    async def operational_check(self, req: OperationalCheckRequest) -> OperationalCheckResponse:
        """Real check: pull live records -> deterministic state -> decision.

        No mock data. The state is the same deterministic object the rest of
        the product uses; the decision is a fixed mapping over it.
        """
        state = await LocationStateService(self.db).get_location_state(
            place=req.location,
            time_window=_internal_window(req.time_window),
        )
        d = decide(
            operational_state=state.operational_state,
            risk_score=state.risk_score,
            confidence=state.confidence,
            time_window=req.time_window,
            operation_type=req.operation_type,
            risk_tolerance=req.risk_tolerance,
        )
        return OperationalCheckResponse(
            decision=d.decision,
            score=d.disruption_score,
            level=d.operational_state,
            confidence=d.confidence,
            coverage_level="limited",
            safe_for_automation=d.safe_for_automation,
            action=d.action,
            reason=d.reason,
            location=state.place,
            operation_type=d.operation_type,
            time_window=req.time_window,
            risk_tolerance=d.risk_tolerance,
            included_sources=INCLUDED_SOURCES,
            excluded_sources=EXCLUDED_SOURCES,
            coverage_warning=_COVERAGE_WARNING,
            brief_id=None,
            computed_at=state.computed_at,
        )

    async def evaluate(self, req: DecisionEvaluateRequest) -> DecisionEvaluateResponse:
        return DecisionEvaluateResponse(
            status="evaluated",
            recommendation="proceed_with_monitoring",
            rationale=(
                "Demo decision endpoint reached after payment-mode handling; "
                "core state, watchlist, and brief endpoints remain ungated."
            ),
            evaluated_at=datetime.now(timezone.utc),
        )
