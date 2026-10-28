from core.db import get_db
from fastapi import APIRouter, Depends
from schemas.feedback import FeedbackCreate, FeedbackResponse
from services.feedback_service import FeedbackService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/", response_model=FeedbackResponse, status_code=201)
async def log_feedback(
    body: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    return await FeedbackService(db).log(body)
