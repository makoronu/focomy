"""Feed routes - RSS, Atom, and JSON feeds."""

import json as json_mod
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.entity import EntityService, QueryParams
from ..services.field import field_service
from ..services.settings import SettingsService
from ..services.theme import theme_service
from ..utils import utcnow

router = APIRouter(tags=["feeds"])


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


def _format_rfc822(iso_date: str) -> str:
    """Convert ISO date string to RFC822 format for RSS feeds."""
    if not iso_date:
        return ""
    try:
        # Handle various ISO formats
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
    except (ValueError, AttributeError):
        return ""


def _build_feed_url(site_url: str, path_prefix: str, slug: str) -> str:
    """Build URL for feed items, avoiding double slashes."""
    parts = [p for p in [site_url.rstrip("/"), path_prefix.strip("/"), slug.strip("/")] if p]
    return "/".join(parts)


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
        url = _build_feed_url(site_url, path_prefix, slug)
        pub_date = _format_rfc822(data.get("created_at", ""))
        items.append(
            f"""
        <item>
            <title><![CDATA[{data.get('title', '')}]]></title>
            <link>{url}</link>
            <description><![CDATA[{data.get('excerpt', '')}]]></description>
            <pubDate>{pub_date}</pubDate>
            <guid>{url}</guid>
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
        url = _build_feed_url(site_url, path_prefix, slug)
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
    updated = entities[0].updated_at.isoformat() if entities else utcnow().isoformat()

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
        url = _build_feed_url(site_url, path_prefix, slug)
        items.append(
            {
                "id": url,
                "url": url,
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
