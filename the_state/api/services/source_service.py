from fastapi import HTTPException
from models.source import Source
from schemas.source import SourceCreate, SourceListResponse, SourceResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


class SourceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_sources(self) -> SourceListResponse:
        result = await self.db.execute(select(Source).order_by(Source.created_at.desc()))
        rows = result.scalars().all()
        total = await self.db.scalar(select(func.count()).select_from(Source))
        return SourceListResponse(
            items=[SourceResponse.model_validate(r) for r in rows],
            total=total or 0,
        )

    async def create_source(self, data: SourceCreate) -> SourceResponse:
        source = Source(
            name=data.name,
            source_type=data.source_type,
            base_url=data.base_url,
            description=data.description,
            meta=data.meta,
        )
        self.db.add(source)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(status_code=409, detail=f"Source '{data.name}' already exists")
        await self.db.refresh(source)
        return SourceResponse.model_validate(source)
