"""Public routes - theme-based content rendering."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.cache import cache_service
from ..services.entity import EntityService, QueryParams
from ..services.field import field_service
from ..services.seo import SEOService
from ..services.theme import theme_service
from ..utils import utcnow
from .helpers import (
    generate_breadcrumbs,
    get_active_theme,
    get_admin_user_optional,
    get_menus_context,
    get_seo_settings,
    get_widgets_context,
    render_theme,
)

router = APIRouter(tags=["public"])


# === Static Assets ===


@router.get("/css/theme.css", response_class=Response)
async def theme_css(db: AsyncSession = Depends(get_db)):
    """Serve theme CSS with caching headers."""
    active_theme = await get_active_theme(db)
    css_content = theme_service.get_css_variables(active_theme)

    return Response(
        content=css_content,
        media_type="text/css",
        headers={
            "Cache-Control": "public, max-age=86400",  # 24 hours
            "Vary": "Accept-Encoding",
        },
    )


# === SEO Routes (must be before dynamic routes) ===


@router.get("/robots.txt", response_class=Response)
async def robots_txt(request: Request):
    """Generate robots.txt dynamically."""
    site_url = str(request.base_url).rstrip("/")

    content = f"""User-agent: *
Allow: /

# Disallow admin and API
Disallow: /admin/
Disallow: /api/

# Sitemap
Sitemap: {site_url}/sitemap.xml
"""
    return Response(content=content, media_type="text/plain")


@router.get("/manifest.json", response_class=Response)
async def manifest_json(request: Request):
    """Generate web app manifest."""
    import json

    site_url = str(request.base_url).rstrip("/")

    manifest = {
        "name": "Focomy",
        "short_name": "Focomy",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#2563eb",
        "icons": [
            {"src": f"{site_url}/static/favicon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": f"{site_url}/static/favicon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }

    return Response(
        content=json.dumps(manifest, ensure_ascii=False, indent=2),
        media_type="application/manifest+json",
    )


@router.get("/sitemap.xml", response_class=Response)
async def sitemap_xml(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Generate sitemap.xml dynamically."""
    entity_svc = EntityService(db)
    site_url = str(request.base_url).rstrip("/")
    seo_svc = SEOService(entity_svc, site_url)

    xml_content = await seo_svc.generate_sitemap()

    return Response(content=xml_content, media_type="application/xml")


# === Preview Routes ===


@router.get("/preview/{token}", response_class=HTMLResponse)
async def preview_entity(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Preview an entity with a valid token (shows draft/unpublished content)."""
    from ..services.preview import get_preview_service

    preview_svc = get_preview_service(db)
    entity = await preview_svc.get_preview_entity(token)

    if not entity:
        raise HTTPException(status_code=404, detail="Preview not found or expired")

    entity_svc = EntityService(db)
    entity_data = entity_svc.serialize(entity)

    # Get content type info
    content_type = entity.type
    ct = field_service.get_content_type(content_type)

    # Get site URL and contexts
    site_url = str(request.base_url).rstrip("/")
    menus_ctx = await get_menus_context(db)
    widgets_ctx = await get_widgets_context(db)
    seo_ctx = await get_seo_settings(db, site_url)

    # Add preview flag to context
    context = {
        "post": entity_data,
        "entity": entity_data,
        "content": entity_data,
        "is_preview": True,
        "content_type": ct,
        **menus_ctx,
        **widgets_ctx,
        **seo_ctx,
    }

    # Determine template
    template = "post.html"
    if ct and ct.template:
        template = ct.template

    html = await render_theme(db, template, context, request=request)

    return HTMLResponse(content=html)


# Cache TTL settings
PAGE_CACHE_TTL = 300  # 5 minutes for pages
LIST_CACHE_TTL = 60  # 1 minute for listings


@router.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def home(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Home page - list recent posts."""
    cache_key = "page:home"
    admin_info = await get_admin_user_optional(request, db)
    if not admin_info:
        cached_html = await cache_service.get(cache_key)
        if cached_html:
            return HTMLResponse(content=cached_html)

    entity_svc = EntityService(db)

    posts = await entity_svc.find(
        "post",
        limit=10,
        order_by="-created_at",
        filters={"status": "published"},
    )

    # Filter by published_at (scheduled posts)
    now = utcnow()
    posts_data = []
    for p in posts:
        data = entity_svc.serialize(p)
        published_at = data.get("published_at")
        # Show if no published_at set or if it's in the past
        if not published_at or datetime.fromisoformat(published_at.replace("Z", "")) <= now:
            posts_data.append(data)

    # Get menus, widgets, and SEO settings
    site_url = str(request.base_url).rstrip("/")
    menus_ctx = await get_menus_context(db)
    widgets_ctx = await get_widgets_context(db)
    seo_ctx = await get_seo_settings(db, site_url)

    html = await render_theme(
        db,
        "home.html",
        {
            "posts": posts_data,
            **menus_ctx,
            **widgets_ctx,
            **seo_ctx,
        },
        request=request,
    )

    await cache_service.set(cache_key, html, LIST_CACHE_TTL)
    return HTMLResponse(content=html)


@router.get("/page/{slug}", response_class=HTMLResponse)
async def view_page(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """View a page."""
    entity_svc = EntityService(db)

    pages = await entity_svc.find(
        "page",
        limit=1,
        filters={"slug": slug},
    )

    if not pages:
        raise HTTPException(status_code=404, detail="Page not found")

    page = pages[0]
    page_data = entity_svc.serialize(page)

    # Get menus and SEO settings first
    site_url = str(request.base_url).rstrip("/")
    menus_ctx = await get_menus_context(db)
    seo_ctx = await get_seo_settings(db, site_url)

    # Generate SEO meta with site settings
    seo_svc = SEOService(entity_svc, site_url, seo_ctx.get("_seo_service_settings", {}))
    meta = seo_svc.generate_meta(page)
    seo_meta = seo_svc.render_meta_tags(meta)

    # Generate breadcrumbs
    breadcrumb_ctx = generate_breadcrumbs(
        [{"name": page_data.get("title", "ページ"), "url": f"/page/{slug}"}], site_url
    )

    html = await render_theme(
        db,
        "post.html",
        {
            "post": page_data,
            "seo_meta": seo_meta,
            **menus_ctx,
            **seo_ctx,
            **breadcrumb_ctx,
        },
        request=request,
        entity=page,
        content_type="page",
    )

    return HTMLResponse(content=html)


# === Category ===


@router.get("/category/{slug}", response_class=HTMLResponse)
async def view_category(
    slug: str,
    request: Request,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    """View posts in a category."""
    entity_svc = EntityService(db)

    # Find category
    categories = await entity_svc.find("category", limit=1, filters={"slug": slug})
    if not categories:
        raise HTTPException(status_code=404, detail="Category not found")

    category = categories[0]
    category_data = entity_svc.serialize(category)

    # Find posts in category (via relation)
    from ..services.relation import RelationService

    relation_svc = RelationService(db)

    per_page = 10
    offset = (page - 1) * per_page

    # Get related posts
    related = await relation_svc.get_related(category.id, "post_categories", reverse=True)
    post_ids = [e.id for e in related]

    # Filter published posts
    posts = []
    for pid in post_ids[offset : offset + per_page]:
        post = await entity_svc.get(pid)
        if post:
            post_data = entity_svc.serialize(post)
            if post_data.get("status") == "published":
                posts.append(post_data)

    total = len(list(post_ids))  # Simplified count
    total_pages = (total + per_page - 1) // per_page

    # Get menus and site context
    site_url = str(request.base_url).rstrip("/")
    menus_ctx = await get_menus_context(db)
    seo_ctx = await get_seo_settings(db, site_url)

    html = await render_theme(
        db,
        "category.html",
        {
            "category": category_data,
            "posts": posts,
            "page": page,
            "total_pages": total_pages,
            **menus_ctx,
            **seo_ctx,
        },
        request=request,
        entity=category,
        content_type="category",
    )

    return HTMLResponse(content=html)


# === Archive ===


@router.get("/archive/{year}/{month}", response_class=HTMLResponse)
async def view_archive(
    year: int,
    month: int,
    request: Request,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    """View posts from a specific month."""
    entity_svc = EntityService(db)

    # Calculate date range
    from datetime import date

    date(year, month, 1)
    if month == 12:
        date(year + 1, 1, 1)
    else:
        date(year, month + 1, 1)

    per_page = 10
    offset = (page - 1) * per_page

    # Find posts in date range
    posts_raw = await entity_svc.find(
        "post",
        limit=per_page,
        offset=offset,
        order_by="-created_at",
        filters={"status": "published"},
    )

    # Filter by date (in-memory for now, ideally use DB filter)
    posts = []
    for p in posts_raw:
        data = entity_svc.serialize(p)
        created = data.get("created_at", "")
        if created and created[:7] == f"{year:04d}-{month:02d}":
            posts.append(data)

    # Get menus and site context
    site_url = str(request.base_url).rstrip("/")
    menus_ctx = await get_menus_context(db)
    seo_ctx = await get_seo_settings(db, site_url)

    html = await render_theme(
        db,
        "archive.html",
        {
            "year": year,
            "month": month,
            "posts": posts,
            "page": page,
            **menus_ctx,
            **seo_ctx,
        },
        request=request,
    )

    return HTMLResponse(content=html)


# === Search ===


@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = "",
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    """Search posts."""
    entity_svc = EntityService(db)

    posts = []
    total = 0

    if q:
        per_page = 10
        offset = (page - 1) * per_page

        # Search in posts
        all_posts = await entity_svc.find(
            "post",
            limit=100,
            order_by="-created_at",
            filters={"status": "published"},
        )

        # Simple in-memory search
        q_lower = q.lower()
        matched = []
        for p in all_posts:
            data = entity_svc.serialize(p)
            title = str(data.get("title", "")).lower()
            excerpt = str(data.get("excerpt", "")).lower()
            if q_lower in title or q_lower in excerpt:
                matched.append(data)

        total = len(matched)
        posts = matched[offset : offset + per_page]

    total_pages = (total + 9) // 10 if total > 0 else 0

    # Get menus and site context
    site_url = str(request.base_url).rstrip("/")
    menus_ctx = await get_menus_context(db)
    seo_ctx = await get_seo_settings(db, site_url)

    html = await render_theme(
        db,
        "search.html",
        {
            "query": q,
            "posts": posts,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            **menus_ctx,
            **seo_ctx,
        },
        request=request,
    )

    return HTMLResponse(content=html)


# === Include sub-routers ===
# Order matters: specific routes first, catch-all routes last

from .routes_feeds import router as feeds_router
from .routes_channels import router as channels_router
from .routes_dynamic import router as dynamic_router

router.include_router(feeds_router)
router.include_router(channels_router)
router.include_router(dynamic_router)  # Must be last (has catch-all patterns)
