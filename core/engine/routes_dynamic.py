"""Dynamic content type routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.cache import cache_service
from ..services.entity import EntityService, QueryParams
from ..services.field import field_service
from ..services.seo import SEOService
from ..services.settings import SettingsService
from ..services.theme import theme_service
from ..utils import utcnow
from .helpers import (
    generate_breadcrumbs,
    get_admin_user_optional,
    get_menus_context,
    get_seo_settings,
    get_widgets_context,
    render_theme,
)

router = APIRouter(tags=["dynamic"])

# Cache TTL settings
PAGE_CACHE_TTL = 300  # 5 minutes for pages
LIST_CACHE_TTL = 60  # 1 minute for listings


# === Dynamic Archive ===


@router.get("/{path_prefix}/archive/{year:int}/{month:int}", response_class=HTMLResponse)
async def content_type_archive(
    path_prefix: str,
    year: int,
    month: int,
    request: Request,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    """Archive for content types with archive_enabled."""
    # Find content type by path prefix
    content_types = field_service.get_all_content_types()
    target_ct = None

    for _ct_name, ct in content_types.items():
        prefix = ct.path_prefix.strip("/")
        if prefix and prefix == path_prefix and ct.archive_enabled:
            target_ct = ct
            break

    if not target_ct:
        raise HTTPException(status_code=404, detail="Archive not found")

    entity_svc = EntityService(db)

    per_page = 10
    offset = (page - 1) * per_page

    # Find entities
    entities_raw = await entity_svc.find(
        target_ct.name,
        limit=per_page,
        offset=offset,
        order_by="-created_at",
        filters={"status": "published"},
    )

    # Filter by date
    posts = []
    for e in entities_raw:
        data = entity_svc.serialize(e)
        created = data.get("created_at", "")
        if created and created[:7] == f"{year:04d}-{month:02d}":
            posts.append(data)

    # Get menus
    menus_ctx = await get_menus_context(db)

    html = await render_theme(
        db,
        "archive.html",
        {
            "year": year,
            "month": month,
            "posts": posts,
            "page": page,
            "content_type": target_ct,
            **menus_ctx,
        },
        request=request,
    )

    return HTMLResponse(content=html)


# === Content Type Listing ===


@router.get("/{path_prefix}", response_class=HTMLResponse)
async def content_type_listing(
    path_prefix: str,
    request: Request,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    """Listing page for content types with path_prefix."""
    # Check cache (only first page) - skip for admin users
    cache_key = f"page:{path_prefix}:list:{page}"
    admin_info = await get_admin_user_optional(request, db)
    if not admin_info:
        cached_html = await cache_service.get(cache_key)
        if cached_html:
            return HTMLResponse(content=cached_html)

    # Find content type by path prefix
    content_types = field_service.get_all_content_types()
    target_ct = None

    for _ct_name, ct in content_types.items():
        prefix = ct.path_prefix.strip("/") if ct.path_prefix else ""
        if prefix and prefix == path_prefix:
            target_ct = ct
            break

    if not target_ct:
        raise HTTPException(status_code=404, detail="Not found")

    entity_svc = EntityService(db)

    per_page = 10
    offset = (page - 1) * per_page

    entities = await entity_svc.find(
        target_ct.name,
        limit=per_page,
        offset=offset,
        order_by="-created_at",
        filters={"status": "published"},
    )

    # Filter by published_at for scheduled posts
    now = utcnow()
    posts_data = []
    for e in entities:
        data = entity_svc.serialize(e)
        published_at = data.get("published_at")
        if not published_at or datetime.fromisoformat(published_at.replace("Z", "")) <= now:
            posts_data.append(data)

    total = await entity_svc.count(target_ct.name, QueryParams(filters={"status": "published"}))
    total_pages = (total + per_page - 1) // per_page

    # Get all contexts
    site_url = str(request.base_url).rstrip("/")
    menus_ctx = await get_menus_context(db)
    widgets_ctx = await get_widgets_context(db)
    seo_ctx = await get_seo_settings(db, site_url)

    html = await render_theme(
        db,
        "home.html",
        {
            "posts": posts_data,
            "content_type": target_ct,
            "page": page,
            "total_pages": total_pages,
            **menus_ctx,
            **widgets_ctx,
            **seo_ctx,
        },
        request=request,
    )

    await cache_service.set(cache_key, html, LIST_CACHE_TTL)
    return HTMLResponse(content=html)


# === Dynamic Content Type Routes ===


@router.get("/{path_prefix:path}/{slug}", response_class=HTMLResponse)
async def view_content_by_path(
    path_prefix: str,
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Dynamic route for content types with path_prefix."""
    # Check cache first - skip for admin users
    cache_key = f"page:{path_prefix}:{slug}"
    admin_info = await get_admin_user_optional(request, db)
    if not admin_info:
        cached_html = await cache_service.get(cache_key)
        if cached_html:
            return HTMLResponse(content=cached_html)

    # Find content type by path prefix
    content_types = field_service.get_all_content_types()

    target_ct = None
    for _ct_name, ct in content_types.items():
        prefix = ct.path_prefix.strip("/") if ct.path_prefix else ""
        if prefix and prefix == path_prefix:
            target_ct = ct
            break

    if not target_ct:
        raise HTTPException(status_code=404, detail="Not found")

    entity_svc = EntityService(db)

    # Find entity by slug
    slug_field = target_ct.slug_field or "slug"
    entities = await entity_svc.find(
        target_ct.name,
        limit=1,
        filters={slug_field: slug, "status": "published"},
    )

    if not entities:
        raise HTTPException(status_code=404, detail="Content not found")

    entity = entities[0]
    entity_data = entity_svc.serialize(entity)

    # Check for scheduled publish (published_at)
    published_at = entity_data.get("published_at")
    if published_at:
        pub_date = datetime.fromisoformat(published_at.replace("Z", ""))
        if pub_date > utcnow():
            raise HTTPException(status_code=404, detail="Content not found")

    # Get site URL and contexts
    site_url = str(request.base_url).rstrip("/")
    menus_ctx = await get_menus_context(db)
    widgets_ctx = await get_widgets_context(db)
    seo_ctx = await get_seo_settings(db, site_url)

    # Generate SEO meta with site settings
    seo_svc = SEOService(entity_svc, site_url, seo_ctx.get("_seo_service_settings", {}))
    meta = seo_svc.generate_meta(entity)
    seo_meta = seo_svc.render_meta_tags(meta)

    # Generate breadcrumbs
    content_url = f"/{path_prefix}/{slug}"
    breadcrumb_ctx = generate_breadcrumbs(
        [{"name": entity_data.get("title", target_ct.label), "url": content_url}], site_url
    )

    # Determine template
    template = target_ct.template or f"{target_ct.name}.html"
    try:
        html = await render_theme(
            db,
            template,
            {
                "post": entity_data,
                "content": entity_data,
                "seo_meta": seo_meta,
                "content_type": target_ct,
                **menus_ctx,
                **widgets_ctx,
                **seo_ctx,
                **breadcrumb_ctx,
            },
            request=request,
            entity=entity,
            content_type=target_ct.name,
        )
    except Exception:
        # Fallback to post.html
        html = await render_theme(
            db,
            "post.html",
            {
                "post": entity_data,
                "seo_meta": seo_meta,
                **menus_ctx,
                **widgets_ctx,
                **seo_ctx,
                **breadcrumb_ctx,
            },
            request=request,
            entity=entity,
            content_type=target_ct.name,
        )

    # Cache the rendered HTML
    await cache_service.set(cache_key, html, PAGE_CACHE_TTL)
    return HTMLResponse(content=html)
