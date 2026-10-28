import uuid

from core.db import get_db
from fastapi import APIRouter, Depends
from schemas.watchlist import (
    WatchlistCreate,
    WatchlistEvaluationResponse,
    WatchlistResponse,
)
from services.watchlist_service import WatchlistService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/", response_model=WatchlistResponse, status_code=201)
async def create_watchlist(
    body: WatchlistCreate,
    db: AsyncSession = Depends(get_db),
) -> WatchlistResponse:
    return await WatchlistService(db).create_watchlist(body)


@router.get("/{watchlist_id}", response_model=WatchlistResponse)
async def get_watchlist(
    watchlist_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> WatchlistResponse:
    return await WatchlistService(db).get_watchlist(watchlist_id)


@router.post("/{watchlist_id}/evaluate", response_model=WatchlistEvaluationResponse)
async def evaluate_watchlist(
    watchlist_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> WatchlistEvaluationResponse:
    return await WatchlistService(db).evaluate_watchlist(watchlist_id)
