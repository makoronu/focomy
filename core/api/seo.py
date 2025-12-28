"""SEO API endpoints - sitemap and meta generation."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.entity import EntityService
from ..services.seo import SEOService

router = APIRouter(tags=["seo"])


def get_site_url(request: Request) -> str:
    """Get site URL from request."""
    return str(request.base_url).rstrip("/")


@router.get("/sitemap.xml")
async def sitemap(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Generate sitemap.xml."""
    entity_svc = EntityService(db)
    seo_svc = SEOService(entity_svc, get_site_url(request))

    content = await seo_svc.generate_sitemap(["post", "page"])

    return Response(
        content=content,
        media_type="application/xml",
    )


@router.get("/api/seo/{entity_type}/{entity_id}")
async def get_seo_meta(
    entity_type: str,
    entity_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get SEO metadata for an entity."""
    entity_svc = EntityService(db)
    entity = await entity_svc.get(entity_id)

    if not entity or entity.type != entity_type:
        return {"error": "Entity not found"}

    seo_svc = SEOService(entity_svc, get_site_url(request))
    return seo_svc.generate_meta(entity)
