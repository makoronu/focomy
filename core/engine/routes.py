"""Public routes - theme-based content rendering."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.cache import cache_service
from ..services.entity import EntityService, QueryParams
from ..services.field import field_service
from ..services.menu import MenuService
from ..services.seo import SEOService
from ..services.settings import SettingsService
from ..services.theme import theme_service
from ..services.widget import WidgetService

router = APIRouter(tags=["public"])


def generate_breadcrumbs(items: list[dict], site_url: str) -> dict:
    """Generate breadcrumb data and JSON-LD.

    Args:
        items: List of {"name": str, "url": str} (relative URLs)
        site_url: Base site URL

    Returns:
        Dict with breadcrumb_items and breadcrumb_json_ld
    """
    import json as json_mod

    # Add home as first item if not present
    breadcrumb_items = []
    if not items or items[0].get("url") != "/":
        breadcrumb_items.append({"name": "ホーム", "url": "/"})

    breadcrumb_items.extend(items)

    # Generate JSON-LD
    json_ld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i + 1,
                "name": item["name"],
                "item": (
                    f"{site_url}{item['url']}"
                    if not item["url"].startswith("http")
                    else item["url"]
                ),
            }
            for i, item in enumerate(breadcrumb_items)
        ],
    }

    return {
        "breadcrumb_items": breadcrumb_items,
        "breadcrumb_json_ld": f'<script type="application/ld+json">{json_mod.dumps(json_ld, ensure_ascii=False)}</script>',
    }


async def get_seo_settings(db: AsyncSession, site_url: str = "") -> dict:
    """Get SEO settings for templates."""
    settings_svc = SettingsService(db)
    seo_settings = await settings_svc.get_by_category("seo")
    site_settings = await settings_svc.get_by_category("site")

    site_name = site_settings.get("name", "Focomy")

    # Settings for SEOService
    seo_service_settings = {
        "name": site_name,
        "description": seo_settings.get("default_description", ""),
        "logo": seo_settings.get("default_og_image", ""),
        "locale": seo_settings.get("og_locale", "ja_JP"),
        "twitter_site": seo_settings.get("twitter_site", ""),
    }

    # Generate site-wide JSON-LD
    entity_svc = EntityService(db)
    seo_svc = SEOService(entity_svc, site_url, seo_service_settings)
    site_json_ld = seo_svc.render_site_json_ld()

    return {
        "seo_settings": {
            "ga4_id": seo_settings.get("ga4_id", ""),
            "gtm_id": seo_settings.get("gtm_id", ""),
            "search_console_id": seo_settings.get("search_console_id", ""),
            "bing_webmaster_id": seo_settings.get("bing_webmaster_id", ""),
            "og_site_name": seo_settings.get("og_site_name", site_name),
            "og_locale": seo_settings.get("og_locale", "ja_JP"),
            "twitter_site": seo_settings.get("twitter_site", ""),
            "default_og_image": seo_settings.get("default_og_image", ""),
            "default_description": seo_settings.get("default_description", ""),
        },
        "site_json_ld": site_json_ld,
        "_seo_service_settings": seo_service_settings,  # For use in routes
    }


async def get_active_theme(db: AsyncSession) -> str:
    """Get active theme name from settings."""
    settings_svc = SettingsService(db)
    theme_settings = await settings_svc.get_by_category("theme")
    return theme_settings.get("active", "default")


async def render_theme(
    db: AsyncSession,
    template_name: str,
    context: dict,
) -> str:
    """Render template with active theme."""
    active_theme = await get_active_theme(db)
    theme_service.set_current_theme(active_theme)

    try:
        return theme_service.render(template_name, context, active_theme)
    except Exception:
        # Fallback to default theme
        return theme_service.render(template_name, context, "default")


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


async def get_menus_context(db: AsyncSession) -> dict:
    """Get menus context for templates."""
    menu_svc = MenuService(db)
    all_menus = await menu_svc.get_all_menus()
    return {
        "menus": {location: [m.to_dict() for m in items] for location, items in all_menus.items()}
    }


async def get_widgets_context(db: AsyncSession) -> dict:
    """Get widgets context for templates."""
    widget_svc = WidgetService(db)
    widgets = await widget_svc.render_all_areas()
    return {"widgets": widgets}


# Cache TTL settings
PAGE_CACHE_TTL = 300  # 5 minutes for pages
LIST_CACHE_TTL = 60  # 1 minute for listings


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
    )

    cache_service.set(cache_key, html, LIST_CACHE_TTL)
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

    # Get menus
    menus_ctx = await get_menus_context(db)

    html = await render_theme(
        db,
        "category.html",
        {
            "category": category_data,
            "posts": posts,
            "page": page,
            "total_pages": total_pages,
            **menus_ctx,
        },
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
            **menus_ctx,
        },
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

    # Get menus
    menus_ctx = await get_menus_context(db)

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
        },
    )

    return HTMLResponse(content=html)


# === RSS Feed ===


@router.get("/feed.xml", response_class=Response)
async def rss_feed(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """RSS feed for posts (default)."""
    return await _generate_rss_feed("post", request, db)


@router.get("/atom.xml", response_class=Response)
async def atom_feed(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Atom feed for posts."""
    return await _generate_atom_feed("post", request, db)


@router.get("/feed.json", response_class=Response)
async def json_feed(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """JSON Feed for posts."""
    return await _generate_json_feed("post", request, db)


@router.get("/{path_prefix}/feed.xml", response_class=Response)
async def content_type_feed(
    path_prefix: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """RSS feed for content types with feed_enabled."""
    content_types = field_service.get_all_content_types()
    target_ct = None

    for _ct_name, ct in content_types.items():
        prefix = ct.path_prefix.strip("/")
        if prefix and prefix == path_prefix and ct.feed_enabled:
            target_ct = ct
            break

    if not target_ct:
        raise HTTPException(status_code=404, detail="Feed not found")

    return await _generate_rss_feed(target_ct.name, request, db)


async def _get_feed_entities(content_type: str, db: AsyncSession) -> tuple:
    """Get entities for feed generation."""
    entity_svc = EntityService(db)
    ct = field_service.get_content_type(content_type)

    entities = await entity_svc.find(
        content_type,
        limit=20,
        order_by="-created_at",
        filters={"status": "published"},
    )

    return entity_svc, ct, entities


async def _generate_rss_feed(
    content_type: str,
    request: Request,
    db: AsyncSession,
) -> Response:
    """Generate RSS 2.0 feed."""
    entity_svc, ct, entities = await _get_feed_entities(content_type, db)
    site_url = str(request.base_url).rstrip("/")
    path_prefix = ct.path_prefix.strip("/") if ct else content_type

    items = []
    for e in entities:
        data = entity_svc.serialize(e)
        slug = data.get("slug", "")
        items.append(
            f"""
        <item>
            <title><![CDATA[{data.get('title', '')}]]></title>
            <link>{site_url}/{path_prefix}/{slug}</link>
            <description><![CDATA[{data.get('excerpt', '')}]]></description>
            <pubDate>{data.get('created_at', '')}</pubDate>
            <guid>{site_url}/{path_prefix}/{slug}</guid>
        </item>"""
        )

    title = ct.label_plural if ct else "Posts"
    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
    <channel>
        <title>{title}</title>
        <link>{site_url}</link>
        <description>Latest {title.lower()}</description>
        <language>ja</language>
        <atom:link href="{site_url}/feed.xml" rel="self" type="application/rss+xml"/>
        {''.join(items)}
    </channel>
</rss>"""

    return Response(content=rss, media_type="application/rss+xml")


async def _generate_atom_feed(
    content_type: str,
    request: Request,
    db: AsyncSession,
) -> Response:
    """Generate Atom feed."""
    entity_svc, ct, entities = await _get_feed_entities(content_type, db)
    site_url = str(request.base_url).rstrip("/")
    path_prefix = ct.path_prefix.strip("/") if ct else content_type

    entries = []
    for e in entities:
        data = entity_svc.serialize(e)
        slug = data.get("slug", "")
        url = f"{site_url}/{path_prefix}/{slug}"
        entries.append(
            f"""
    <entry>
        <title><![CDATA[{data.get('title', '')}]]></title>
        <link href="{url}"/>
        <id>{url}</id>
        <updated>{data.get('updated_at', data.get('created_at', ''))}</updated>
        <summary><![CDATA[{data.get('excerpt', '')}]]></summary>
    </entry>"""
        )

    title = ct.label_plural if ct else "Posts"
    updated = entities[0].updated_at.isoformat() if entities else ""

    atom = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
    <title>{title}</title>
    <link href="{site_url}"/>
    <link href="{site_url}/atom.xml" rel="self"/>
    <id>{site_url}/</id>
    <updated>{updated}</updated>
    {''.join(entries)}
</feed>"""

    return Response(content=atom, media_type="application/atom+xml")


async def _generate_json_feed(
    content_type: str,
    request: Request,
    db: AsyncSession,
) -> Response:
    """Generate JSON Feed (https://jsonfeed.org/)."""
    import json

    entity_svc, ct, entities = await _get_feed_entities(content_type, db)
    site_url = str(request.base_url).rstrip("/")
    path_prefix = ct.path_prefix.strip("/") if ct else content_type

    items = []
    for e in entities:
        data = entity_svc.serialize(e)
        slug = data.get("slug", "")
        items.append(
            {
                "id": f"{site_url}/{path_prefix}/{slug}",
                "url": f"{site_url}/{path_prefix}/{slug}",
                "title": data.get("title", ""),
                "content_text": data.get("excerpt", ""),
                "date_published": data.get("created_at", ""),
                "date_modified": data.get("updated_at", data.get("created_at", "")),
            }
        )

    title = ct.label_plural if ct else "Posts"
    feed = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": title,
        "home_page_url": site_url,
        "feed_url": f"{site_url}/feed.json",
        "language": "ja",
        "items": items,
    }

    return Response(
        content=json.dumps(feed, ensure_ascii=False, indent=2), media_type="application/feed+json"
    )


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
    # Check cache (only first page)
    cache_key = f"page:{path_prefix}:list:{page}"
    cached_html = cache_service.get(cache_key)
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
    now = datetime.utcnow()
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
    )

    cache_service.set(cache_key, html, LIST_CACHE_TTL)
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
    # Check cache first
    cache_key = f"page:{path_prefix}:{slug}"
    cached_html = cache_service.get(cache_key)
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
        if pub_date > datetime.utcnow():
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
        )

    # Cache the rendered HTML
    cache_service.set(cache_key, html, PAGE_CACHE_TTL)
    return HTMLResponse(content=html)
