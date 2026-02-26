"""Engine route helpers - shared utilities for public routes."""

from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.auth import AuthService
from ..services.entity import EntityService, QueryParams
from ..services.field import field_service
from ..services.menu import MenuService
from ..services.seo import SEOService
from ..services.settings import SettingsService
from ..services.theme import theme_service
from ..services.widget import WidgetService
from ..utils import utcnow


async def get_admin_user_optional(
    request: Request,
    db: AsyncSession,
) -> dict | None:
    """Get admin user from session if logged in (optional, no error)."""
    token = request.cookies.get("session")
    if not token:
        return None

    auth_svc = AuthService(db)
    user = await auth_svc.get_current_user(token)
    if not user:
        return None

    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(user)
    if user_data.get("role") not in ("admin", "editor", "author"):
        return None

    return {"user": user, "user_data": user_data}


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
        "site": {
            "name": site_name,
            "tagline": site_settings.get("tagline", ""),
            "language": site_settings.get("language", "ja"),
        },
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
    request: Request = None,
    entity=None,
    content_type: str = None,
) -> str:
    """Render template with active theme."""
    active_theme = await get_active_theme(db)
    theme_service.set_current_theme(active_theme)

    # Set site_name from context or settings
    if "site" in context and "name" in context["site"]:
        context.setdefault("site_name", context["site"]["name"])

    # Add admin bar context if logged in
    if request:
        admin_info = await get_admin_user_optional(request, db)
        if admin_info:
            context["is_admin"] = True
            context["admin_user"] = admin_info["user_data"]
            context["active_theme"] = active_theme  # For customize link
            context["csrf_token"] = getattr(request.state, "csrf_token", "")  # For API calls
            # Build edit URL if entity provided
            if entity and content_type:
                context["edit_url"] = f"/admin/{content_type}/{entity.id}/edit"
            # Add content_types for admin bar dropdown
            all_ct = field_service.get_all_content_types()
            context["content_types"] = {
                name: ct.model_dump()
                for name, ct in all_ct.items()
                if ct.admin_menu  # Only show types with admin_menu=true
            }
        else:
            context["is_admin"] = False

    try:
        return theme_service.render(template_name, context, active_theme)
    except Exception:
        # Fallback to default theme
        return theme_service.render(template_name, context, "default")


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
