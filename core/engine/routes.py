"""Public routes - theme-based content rendering."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.entity import EntityService, QueryParams
from ..services.seo import SEOService
from ..services.theme import theme_service
from ..services.field import field_service
from ..services.cache import cache_service
from ..services.menu import MenuService
from ..services.widget import WidgetService


router = APIRouter(tags=["public"])


async def get_menus_context(db: AsyncSession) -> dict:
    """Get menus context for templates."""
    menu_svc = MenuService(db)
    all_menus = await menu_svc.get_all_menus()
    return {
        "menus": {
            location: [m.to_dict() for m in items]
            for location, items in all_menus.items()
        }
    }


async def get_widgets_context(db: AsyncSession) -> dict:
    """Get widgets context for templates."""
    widget_svc = WidgetService(db)
    widgets = await widget_svc.render_all_areas()
    return {"widgets": widgets}

# Cache TTL settings
PAGE_CACHE_TTL = 300  # 5 minutes for pages
LIST_CACHE_TTL = 60   # 1 minute for listings


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Home page - list recent posts."""
    cache_key = "page:home"
    cached_html = cache_service.get(cache_key)
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
    now = datetime.utcnow()
    posts_data = []
    for p in posts:
        data = entity_svc.serialize(p)
        published_at = data.get("published_at")
        # Show if no published_at set or if it's in the past
        if not published_at or datetime.fromisoformat(published_at.replace("Z", "")) <= now:
            posts_data.append(data)

    # Get menus and widgets
    menus_ctx = await get_menus_context(db)
    widgets_ctx = await get_widgets_context(db)

    html = theme_service.render("index.html", {
        "posts": posts_data,
        **menus_ctx,
        **widgets_ctx,
    })

    cache_service.set(cache_key, html, LIST_CACHE_TTL)
    return HTMLResponse(content=html)


@router.get("/post/{slug}", response_class=HTMLResponse)
async def view_post(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """View a single post."""
    cache_key = f"page:post:{slug}"
    cached_html = cache_service.get(cache_key)
    if cached_html:
        return HTMLResponse(content=cached_html)

    entity_svc = EntityService(db)

    # Find post by slug
    posts = await entity_svc.find(
        "post",
        limit=1,
        filters={"slug": slug},
    )

    if not posts:
        raise HTTPException(status_code=404, detail="Post not found")

    post = posts[0]
    post_data = entity_svc.serialize(post)

    # Check if post is published and not scheduled for future
    if post_data.get("status") != "published":
        raise HTTPException(status_code=404, detail="Post not found")

    published_at = post_data.get("published_at")
    if published_at:
        pub_date = datetime.fromisoformat(published_at.replace("Z", ""))
        if pub_date > datetime.utcnow():
            raise HTTPException(status_code=404, detail="Post not found")

    # Generate SEO meta
    site_url = str(request.base_url).rstrip("/")
    seo_svc = SEOService(entity_svc, site_url)
    meta = seo_svc.generate_meta(post)
    seo_meta = seo_svc.render_meta_tags(meta)

    # Get menus
    menus_ctx = await get_menus_context(db)

    html = theme_service.render("post.html", {
        "post": post_data,
        "seo_meta": seo_meta,
        **menus_ctx,
    })

    cache_service.set(cache_key, html, PAGE_CACHE_TTL)
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

    # Generate SEO meta
    site_url = str(request.base_url).rstrip("/")
    seo_svc = SEOService(entity_svc, site_url)
    meta = seo_svc.generate_meta(page)
    seo_meta = seo_svc.render_meta_tags(meta)

    # Get menus
    menus_ctx = await get_menus_context(db)

    html = theme_service.render("post.html", {
        "post": page_data,
        "seo_meta": seo_meta,
        **menus_ctx,
    })

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
    for pid in post_ids[offset:offset + per_page]:
        post = await entity_svc.get(pid)
        if post:
            post_data = entity_svc.serialize(post)
            if post_data.get("status") == "published":
                posts.append(post_data)

    total = len([pid for pid in post_ids])  # Simplified count
    total_pages = (total + per_page - 1) // per_page

    # Get menus
    menus_ctx = await get_menus_context(db)

    html = theme_service.render("category.html", {
        "category": category_data,
        "posts": posts,
        "page": page,
        "total_pages": total_pages,
        **menus_ctx,
    })

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
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)

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

    # Get menus
    menus_ctx = await get_menus_context(db)

    html = theme_service.render("archive.html", {
        "year": year,
        "month": month,
        "posts": posts,
        "page": page,
        **menus_ctx,
    })

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
        posts = matched[offset:offset + per_page]

    total_pages = (total + 9) // 10 if total > 0 else 0

    # Get menus
    menus_ctx = await get_menus_context(db)

    html = theme_service.render("search.html", {
        "query": q,
        "posts": posts,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        **menus_ctx,
    })

    return HTMLResponse(content=html)


# === RSS Feed ===

@router.get("/feed.xml", response_class=Response)
async def rss_feed(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """RSS feed for posts (default)."""
    return await _generate_feed("post", request, db)


@router.get("/{path_prefix}/feed.xml", response_class=Response)
async def content_type_feed(
    path_prefix: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """RSS feed for content types with feed_enabled."""
    # Find content type by path prefix
    content_types = field_service.get_all_content_types()
    target_ct = None

    for ct_name, ct in content_types.items():
        prefix = ct.path_prefix.strip("/")
        if prefix and prefix == path_prefix and ct.feed_enabled:
            target_ct = ct
            break

    if not target_ct:
        raise HTTPException(status_code=404, detail="Feed not found")

    return await _generate_feed(target_ct.name, request, db)


async def _generate_feed(
    content_type: str,
    request: Request,
    db: AsyncSession,
) -> Response:
    """Generate RSS feed for a content type."""
    entity_svc = EntityService(db)
    ct = field_service.get_content_type(content_type)

    entities = await entity_svc.find(
        content_type,
        limit=20,
        order_by="-created_at",
        filters={"status": "published"},
    )

    site_url = str(request.base_url).rstrip("/")
    path_prefix = ct.path_prefix.strip("/") if ct else content_type

    items = []
    for e in entities:
        data = entity_svc.serialize(e)
        slug = data.get("slug", "")
        items.append(f"""
        <item>
            <title><![CDATA[{data.get('title', '')}]]></title>
            <link>{site_url}/{path_prefix}/{slug}</link>
            <description><![CDATA[{data.get('excerpt', '')}]]></description>
            <pubDate>{data.get('created_at', '')}</pubDate>
            <guid>{site_url}/{path_prefix}/{slug}</guid>
        </item>""")

    title = ct.label_plural if ct else "Posts"
    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
    <channel>
        <title>{title}</title>
        <link>{site_url}</link>
        <description>Latest {title.lower()}</description>
        <language>ja</language>
        {''.join(items)}
    </channel>
</rss>"""

    return Response(content=rss, media_type="application/xml")


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

    for ct_name, ct in content_types.items():
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

    html = theme_service.render("archive.html", {
        "year": year,
        "month": month,
        "posts": posts,
        "page": page,
        "content_type": target_ct,
        **menus_ctx,
    })

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
    # Find content type by path prefix
    content_types = field_service.get_all_content_types()
    target_ct = None

    for ct_name, ct in content_types.items():
        prefix = ct.path_prefix.strip("/")
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
    now = datetime.utcnow()
    posts_data = []
    for e in entities:
        data = entity_svc.serialize(e)
        published_at = data.get("published_at")
        if not published_at or datetime.fromisoformat(published_at.replace("Z", "")) <= now:
            posts_data.append(data)

    total = await entity_svc.count(target_ct.name, QueryParams(filters={"status": "published"}))
    total_pages = (total + per_page - 1) // per_page

    # Get menus
    menus_ctx = await get_menus_context(db)

    html = theme_service.render("index.html", {
        "posts": posts_data,
        "content_type": target_ct,
        "page": page,
        "total_pages": total_pages,
        **menus_ctx,
    })

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
    # Find content type by path prefix
    content_types = field_service.get_all_content_types()

    target_ct = None
    for ct_name, ct in content_types.items():
        prefix = ct.path_prefix.strip("/")
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

    # Generate SEO meta
    site_url = str(request.base_url).rstrip("/")
    seo_svc = SEOService(entity_svc, site_url)
    meta = seo_svc.generate_meta(entity)
    seo_meta = seo_svc.render_meta_tags(meta)

    # Get menus
    menus_ctx = await get_menus_context(db)

    # Determine template
    template = target_ct.template or f"{target_ct.name}.html"
    try:
        html = theme_service.render(template, {
            "post": entity_data,
            "content": entity_data,
            "seo_meta": seo_meta,
            "content_type": target_ct,
            **menus_ctx,
        })
    except Exception:
        # Fallback to post.html
        html = theme_service.render("post.html", {
            "post": entity_data,
            "seo_meta": seo_meta,
            **menus_ctx,
        })

    return HTMLResponse(content=html)
