from __future__ import annotations

from fastapi import HTTPException
from models.brief import Brief
from models.feedback_log import FeedbackLog
from schemas.feedback import FeedbackCreate, FeedbackResponse
from sqlalchemy.ext.asyncio import AsyncSession

from services.scoring_calibration_service import refresh_weight_cache


class FeedbackService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log(self, body: FeedbackCreate) -> FeedbackResponse:
        brief = await self.db.get(Brief, body.brief_id)
        if brief is None:
            raise HTTPException(status_code=404, detail="Brief not found")

        feedback = FeedbackLog(
            brief_id=brief.id,
            watched_entity_id=brief.watched_entity_id,
            acknowledged=body.acknowledged,
            action_taken=body.action_taken,
            false_positive=body.false_positive,
            false_negative=body.false_negative,
            notes=body.notes,
            outcome=body.outcome,
        )
        self.db.add(feedback)
        await self.db.commit()
        await self.db.refresh(feedback)

        # Close the flywheel: feedback immediately recalibrates the weights.
        await refresh_weight_cache(self.db)

        return FeedbackResponse.model_validate(feedback)
