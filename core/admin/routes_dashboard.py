"""Admin dashboard and media routes."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import get_db
from ..models import Entity
from ..services.entity import EntityService
from ..services.field import field_service
from ..utils import require_feature
from .helpers import templates, require_admin, get_context

router = APIRouter()


# === Dashboard ===


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Dashboard page."""
    entity_svc = EntityService(db)
    content_types = field_service.get_all_content_types()

    # Get stats for each content type
    stats = {}
    for ct_name in content_types.keys():
        stats[ct_name] = await entity_svc.count(ct_name)

    # Get recent posts with channel info
    from ..services.relation import RelationService

    relation_svc = RelationService(db)
    recent_posts = []
    posts = await entity_svc.find("post", limit=5, order_by="-created_at")
    for post in posts:
        data = entity_svc.serialize(post)
        # Get channel for this post
        related_channels = await relation_svc.get_related(post.id, "post_channel")
        if related_channels:
            channel_data = entity_svc.serialize(related_channels[0])
            data["channel_slug"] = channel_data.get("slug")
            data["channel_title"] = channel_data.get("title")
        recent_posts.append(data)

    # Check for updates
    from ..services.update import update_service

    update_info = await update_service.check_for_updates()

    context = await get_context(request, db, current_user, "dashboard")
    context.update(
        {
            "stats": stats,
            "recent_posts": recent_posts,
            "update_info": {
                "current_version": update_info.current_version,
                "latest_version": update_info.latest_version,
                "has_update": update_info.has_update,
                "release_url": update_info.release_url,
            },
        }
    )

    return templates.TemplateResponse("admin/dashboard.html", context)


# === Media ===


@router.get("/media", response_class=HTMLResponse)
async def media_list(
    request: Request,
    page: int = 1,
    q: str = "",
    type: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Media library page."""
    require_feature("media")
    from ..services.media import MediaService

    media_svc = MediaService(db)

    per_page = get_settings().admin.per_page
    offset = (page - 1) * per_page

    # Prepare filters
    mime_type = f"{type}/" if type else None
    search = q if q else None

    items = await media_svc.find(limit=per_page, offset=offset, mime_type=mime_type, search=search)
    total = await media_svc.count(mime_type=mime_type, search=search)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 0

    context = await get_context(request, db, current_user, "media")
    context.update(
        {
            "items": [media_svc.serialize(m) for m in items],
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "message": request.query_params.get("message"),
            "search_query": q,
            "type_filter": type,
        }
    )

    return templates.TemplateResponse("admin/media.html", context)
