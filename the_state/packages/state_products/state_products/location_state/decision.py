"""Deterministic operational decision.

Layered on the deterministic LocationState - it never introduces
probability or an LLM. Same state + same inputs => same decision. This is
the "can I execute this operation here, right now?" answer.
"""

from __future__ import annotations

from dataclasses import dataclass

from state_products.location_state.schema import OperationalState

# Severity ladder. The decision is the band, optionally shifted one rung by
# the caller's risk tolerance.
_LADDER = ["proceed", "proceed_with_caution", "hold", "escalate"]

_BASE: dict[OperationalState, str] = {
    OperationalState.NORMAL: "proceed",
    OperationalState.ELEVATED: "proceed_with_caution",
    OperationalState.WATCH: "hold",
    OperationalState.DISRUPTED: "hold",
    OperationalState.CRITICAL: "escalate",
}

_AUTOMATION = {
    "proceed": "low_risk_only",
    "proceed_with_caution": "supervised_only",
    "hold": "no",
    "escalate": "no",
}

_ACTION = {
    "proceed": "Dispatch as planned. Monitor for street-closure changes.",
    "proceed_with_caution": (
        "Dispatch with added monitoring; brief the crew on active closures and events in the area."
    ),
    "hold": (
        "Hold dispatch; reassess after the next refresh, or choose an "
        "alternate area or time window."
    ),
    "escalate": "Escalate to a human decision-maker before any dispatch.",
}

# Risk tolerance shifts the rung: a risk-averse caller is moved one step
# more conservative, a risk-tolerant one step less (never below HOLD once
# real disruption is present).
_TOLERANCE_SHIFT = {"low": +1, "normal": 0, "high": -1}

VALID_OPERATIONS = (
    "field_dispatch",
    "crew_routing",
    "site_visit",
    "delivery",
    "general",
)
VALID_TOLERANCE = ("low", "normal", "high")


@dataclass(frozen=True)
class OperationalDecision:
    decision: str  # one of _LADDER
    disruption_score: int  # 0-100, from risk_score
    operational_state: str
    confidence: str  # high | medium | low
    reason: str
    action: str
    safe_for_automation: str  # low_risk_only | supervised_only | no
    operation_type: str
    time_window: str
    risk_tolerance: str


def _confidence_word(confidence: float) -> str:
    if confidence >= 0.66:
        return "high"
    if confidence >= 0.33:
        return "medium"
    return "low"


def decide(
    *,
    operational_state: OperationalState | str,
    risk_score: float,
    confidence: float,
    time_window: str,
    operation_type: str = "field_dispatch",
    risk_tolerance: str = "normal",
) -> OperationalDecision:
    state = (
        operational_state
        if isinstance(operational_state, OperationalState)
        else OperationalState(str(operational_state).lower())
    )
    tolerance = risk_tolerance if risk_tolerance in VALID_TOLERANCE else "normal"
    operation = operation_type if operation_type in VALID_OPERATIONS else "general"

    base_idx = _LADDER.index(_BASE[state])
    shifted = base_idx + _TOLERANCE_SHIFT[tolerance]
    # Relaxation can never drop a real-disruption state below HOLD.
    floor = 2 if state in (OperationalState.WATCH, OperationalState.DISRUPTED) else 0
    idx = max(floor if _TOLERANCE_SHIFT[tolerance] < 0 else 0, min(len(_LADDER) - 1, shifted))
    decision = _LADDER[idx]

    if decision == "proceed":
        reason = (
            "No high-severity disruption was detected in the connected "
            "public records for the selected window."
        )
    elif decision == "proceed_with_caution":
        reason = (
            "Low-to-moderate disruption signals are present in the "
            "connected public records for the selected window."
        )
    elif decision == "hold":
        reason = (
            "Material disruption was detected in the connected public "
            "records for the selected window."
        )
    else:
        reason = (
            "Severe disruption was detected; this exceeds an automatable "
            "threshold and needs human review."
        )

    return OperationalDecision(
        decision=decision,
        disruption_score=round(max(0.0, min(1.0, risk_score)) * 100),
        operational_state=state.value,
        confidence=_confidence_word(confidence),
        reason=reason,
        action=_ACTION[decision],
        safe_for_automation=_AUTOMATION[decision],
        operation_type=operation,
        time_window=time_window,
        risk_tolerance=tolerance,
    )
