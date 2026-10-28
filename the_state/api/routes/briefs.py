import uuid

from core.db import get_db
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from schemas.brief import BriefGenerateRequest, BriefResponse, BriefVerification
from services.brief_service import BriefService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/generate", response_model=BriefResponse, status_code=201)
async def generate_brief(
    body: BriefGenerateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BriefResponse:
    service = BriefService(db)
    brief = await service.generate(body=body)
    return await service.to_response(brief, url=_brief_url(request, brief.id))


@router.get("/{brief_id}/view", response_class=HTMLResponse)
async def view_brief(
    brief_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    # Public, no auth: this page is the citable audit artifact.
    service = BriefService(db)
    brief = await service.get(brief_id)
    return HTMLResponse(content=await service.render_html(brief))


@router.get("/{brief_id}/verify", response_model=BriefVerification)
async def verify_brief(
    brief_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> BriefVerification:
    # Public, no auth: a checkable attestation, not a claim to be trusted.
    service = BriefService(db)
    brief = await service.get(brief_id)
    return await service.verify(brief)


@router.get("/{brief_id}", response_model=BriefResponse)
async def get_brief(
    brief_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> BriefResponse:
    service = BriefService(db)
    brief = await service.get(brief_id)
    return await service.to_response(brief, url=_brief_url(request, brief.id))


def _brief_url(request: Request, brief_id: uuid.UUID) -> str:
    return str(request.url_for("get_brief", brief_id=str(brief_id)))
