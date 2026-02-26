"""Channel and series routes."""

import json as json_mod
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.cache import cache_service
from ..services.entity import EntityService, QueryParams
from ..services.field import field_service
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
from .routes_feeds import _build_feed_url, _format_rfc822

router = APIRouter(tags=["channels"])


@router.get("/channel/{channel_slug}", response_class=HTMLResponse)
async def channel_list(
    channel_slug: str,
    request: Request,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
):
    """Channel post list."""
    entity_svc = EntityService(db)
    from ..services.relation import RelationService

    relation_svc = RelationService(db)

    # Get channel by slug
    channels = await entity_svc.find("channel", limit=1, filters={"slug": channel_slug})
    if not channels:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel = channels[0]
    channel_data = entity_svc.serialize(channel)

    # Get all published posts and filter by channel relation
    per_page = 10
    offset = (page - 1) * per_page

    all_posts = await entity_svc.find(
        "post",
        limit=1000,
        order_by="-published_at",
        filters={"status": "published"},
    )

    # Filter by channel relation
    channel_posts = []
    for post in all_posts:
        related_channels = await relation_svc.get_related(post.id, "post_channel")
        if any(c.id == channel.id for c in related_channels):
            channel_posts.append(post)

    total = len(channel_posts)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    paginated_posts = channel_posts[offset : offset + per_page]
    entities = [entity_svc.serialize(p) for p in paginated_posts]

    # Get menus, widgets, and SEO settings
    site_url = str(request.base_url).rstrip("/")
    menus_ctx = await get_menus_context(db)
    widgets_ctx = await get_widgets_context(db)
    seo_data = await get_seo_settings(db, site_url)

    # Breadcrumbs
    breadcrumb_data = generate_breadcrumbs(
        [
            {"name": channel_data.get("title", channel_slug), "url": f"/channel/{channel_slug}"},
        ],
        site_url,
    )

    html = await render_theme(
        db,
        "channel.html",
        {
            "channel": channel_data,
            "entities": entities,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "channel_slug": channel_slug,
            **menus_ctx,
            **widgets_ctx,
            **seo_data,
            **breadcrumb_data,
        },
        request=request,
        entity=channel,
        content_type="channel",
    )
    return HTMLResponse(content=html)


@router.get("/channel/{channel_slug}/feed.xml", response_class=Response)
async def channel_feed(
    channel_slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """RSS feed for channel."""
    entity_svc = EntityService(db)
    from ..services.relation import RelationService

    relation_svc = RelationService(db)

    # Get channel by slug
    channels = await entity_svc.find("channel", limit=1, filters={"slug": channel_slug})
    if not channels:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel = channels[0]
    channel_data = entity_svc.serialize(channel)

    # Get published posts for this channel
    all_posts = await entity_svc.find(
        "post",
        limit=1000,
        order_by="-published_at",
        filters={"status": "published"},
    )

    channel_posts = []
    for post in all_posts:
        related_channels = await relation_svc.get_related(post.id, "post_channel")
        if any(c.id == channel.id for c in related_channels):
            channel_posts.append(post)

    # Limit to 20 items
    channel_posts = channel_posts[:20]

    # Generate RSS using raw XML (same as _generate_rss_feed)
    site_url = str(request.base_url).rstrip("/")

    items = []
    for post in channel_posts:
        post_data = entity_svc.serialize(post)
        slug = post_data.get("slug", "")
        url = f"{site_url}/channel/{channel_slug}/{slug}"
        pub_date = _format_rfc822(post_data.get("published_at", ""))
        items.append(
            f"""
        <item>
            <title><![CDATA[{post_data.get('title', '')}]]></title>
            <link>{url}</link>
            <description><![CDATA[{post_data.get('excerpt', '')}]]></description>
            <pubDate>{pub_date}</pubDate>
            <guid>{url}</guid>
        </item>"""
        )

    channel_title = channel_data.get("title", channel_slug)
    channel_desc = channel_data.get("description", f"Latest posts from {channel_title}")
    feed_url = f"{site_url}/channel/{channel_slug}/feed.xml"

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
    <channel>
        <title>{channel_title}</title>
        <link>{site_url}/channel/{channel_slug}</link>
        <description>{channel_desc}</description>
        <language>ja</language>
        <atom:link href="{feed_url}" rel="self" type="application/rss+xml"/>
        {''.join(items)}
    </channel>
</rss>"""

    return Response(content=rss, media_type="application/rss+xml")


@router.get("/channel/{channel_slug}/{post_slug}", response_class=HTMLResponse)
async def channel_post_detail(
    channel_slug: str,
    post_slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Channel post detail page."""
    entity_svc = EntityService(db)
    from ..services.relation import RelationService

    relation_svc = RelationService(db)

    # Get channel by slug
    channels = await entity_svc.find("channel", limit=1, filters={"slug": channel_slug})
    if not channels:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel = channels[0]
    channel_data = entity_svc.serialize(channel)

    # Get post by slug
    posts = await entity_svc.find(
        "post",
        limit=1,
        filters={"slug": post_slug, "status": "published"},
    )
    if not posts:
        raise HTTPException(status_code=404, detail="Post not found")
    post = posts[0]

    # Verify post belongs to this channel
    related_channels = await relation_svc.get_related(post.id, "post_channel")
    if not any(c.id == channel.id for c in related_channels):
        raise HTTPException(status_code=404, detail="Post not found in this channel")

    post_data = entity_svc.serialize(post)

    # Get series info if any
    series_data = None
    series_posts = []
    related_series = await relation_svc.get_related(post.id, "post_series")
    if related_series:
        series = related_series[0]
        series_data = entity_svc.serialize(series)

        # Get all posts in series
        all_posts = await entity_svc.find(
            "post",
            limit=100,
            order_by="series_order",
            filters={"status": "published"},
        )
        for p in all_posts:
            p_series = await relation_svc.get_related(p.id, "post_series")
            if any(s.id == series.id for s in p_series):
                series_posts.append(entity_svc.serialize(p))

    # Get author
    author_data = None
    related_authors = await relation_svc.get_related(post.id, "post_author")
    if related_authors:
        author_data = entity_svc.serialize(related_authors[0])

    # Get tags
    tags = []
    related_tags = await relation_svc.get_related(post.id, "post_tags")
    for tag in related_tags:
        tags.append(entity_svc.serialize(tag))

    # Get menus, widgets, and SEO settings
    site_url = str(request.base_url).rstrip("/")
    menus_ctx = await get_menus_context(db)
    widgets_ctx = await get_widgets_context(db)
    seo_data = await get_seo_settings(db, site_url)

    # Breadcrumbs
    breadcrumb_data = generate_breadcrumbs(
        [
            {"name": channel_data.get("title", channel_slug), "url": f"/channel/{channel_slug}"},
            {"name": post_data.get("title", "記事"), "url": f"/channel/{channel_slug}/{post_slug}"},
        ],
        site_url,
    )

    html = await render_theme(
        db,
        "post.html",
        {
            "entity": post_data,
            "channel": channel_data,
            "author": author_data,
            "tags": tags,
            "series": series_data,
            "series_posts": series_posts,
            "channel_slug": channel_slug,
            **menus_ctx,
            **widgets_ctx,
            **seo_data,
            **breadcrumb_data,
        },
        request=request,
        entity=post,
        content_type="post",
    )
    return HTMLResponse(content=html)


@router.get("/series/{series_slug}", response_class=HTMLResponse)
async def series_list(
    series_slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Series post list."""
    entity_svc = EntityService(db)
    from ..services.relation import RelationService

    relation_svc = RelationService(db)

    # Get series by slug
    series_list = await entity_svc.find("series", limit=1, filters={"slug": series_slug})
    if not series_list:
        raise HTTPException(status_code=404, detail="Series not found")
    series = series_list[0]
    series_data = entity_svc.serialize(series)

    # Get all published posts in series, ordered by series_order
    all_posts = await entity_svc.find(
        "post",
        limit=100,
        order_by="series_order",
        filters={"status": "published"},
    )

    series_posts = []
    for post in all_posts:
        related_series = await relation_svc.get_related(post.id, "post_series")
        if any(s.id == series.id for s in related_series):
            post_data = entity_svc.serialize(post)
            # Get channel for URL
            related_channels = await relation_svc.get_related(post.id, "post_channel")
            if related_channels:
                channel_data = entity_svc.serialize(related_channels[0])
                post_data["channel_slug"] = channel_data.get("slug")
            series_posts.append(post_data)

    # Get channel info for series
    channel_data = None
    related_channels = await relation_svc.get_related(series.id, "series_channel")
    if related_channels:
        channel_data = entity_svc.serialize(related_channels[0])

    # Get menus, widgets, and SEO settings
    site_url = str(request.base_url).rstrip("/")
    menus_ctx = await get_menus_context(db)
    widgets_ctx = await get_widgets_context(db)
    seo_data = await get_seo_settings(db, site_url)

    # Breadcrumbs
    breadcrumb_items = [{"name": "シリーズ", "url": "/series"}]
    if channel_data:
        breadcrumb_items.insert(0, {"name": channel_data.get("title"), "url": f"/channel/{channel_data.get('slug')}"})
    breadcrumb_items.append({"name": series_data.get("title", series_slug), "url": f"/series/{series_slug}"})
    breadcrumb_data = generate_breadcrumbs(breadcrumb_items, site_url)

    html = await render_theme(
        db,
        "series.html",
        {
            "series": series_data,
            "entities": series_posts,
            "channel": channel_data,
            **menus_ctx,
            **widgets_ctx,
            **seo_data,
            **breadcrumb_data,
        },
        request=request,
        entity=series,
        content_type="series",
    )
    return HTMLResponse(content=html)
