from core.db import get_db
from fastapi import APIRouter, Depends
from schemas.source import SourceCreate, SourceListResponse, SourceResponse
from services.source_service import SourceService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/", response_model=SourceListResponse)
async def list_sources(db: AsyncSession = Depends(get_db)):
    return await SourceService(db).list_sources()


@router.post("/", response_model=SourceResponse, status_code=201)
async def create_source(body: SourceCreate, db: AsyncSession = Depends(get_db)):
    return await SourceService(db).create_source(body)
