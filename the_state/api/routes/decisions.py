from core.db import get_db
from fastapi import APIRouter, Depends
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
from services.decision_service import DecisionService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/check", response_model=OperationalCheckResponse)
async def operational_check(
    body: OperationalCheckRequest,
    db: AsyncSession = Depends(get_db),
) -> OperationalCheckResponse:
    """The pre-action check: can this operation execute here, right now?"""
    resp = await DecisionService(db).operational_check(body)
    # Persist the append-only snapshot the state read flushed.
    await db.commit()
    return resp


@router.post("/risk-score", response_model=RiskScoreResponse)
async def score_risk(body: RiskScoreRequest, db: AsyncSession = Depends(get_db)):
    """Calculate placeholder risk score for a given area or incident."""
    svc = DecisionService(db)
    return await svc.score_risk(body)


@router.post("/sitrep", response_model=SitrepResponse)
async def generate_sitrep(body: SitrepRequest, db: AsyncSession = Depends(get_db)):
    """Generate a placeholder incident situation report."""
    svc = DecisionService(db)
    return await svc.generate_sitrep(body)


@router.post("/evaluate", response_model=DecisionEvaluateResponse)
async def evaluate_decision(
    body: DecisionEvaluateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Payment-mode demo endpoint. Only this route is gated in v0."""
    svc = DecisionService(db)
    return await svc.evaluate(body)
