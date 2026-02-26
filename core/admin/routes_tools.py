"""Admin tools routes - sitemap, link validator."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Entity
from ..services.entity import EntityService
from ..utils import require_feature
from .helpers import templates, require_admin, get_context

router = APIRouter()


# === Sitemap Management ===


@router.get("/tools/sitemap", response_class=HTMLResponse)
async def sitemap_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Sitemap management page."""
    from ..services.seo import SEOService
    from ..services.settings import SettingsService

    site_url = str(request.base_url).rstrip("/")
    entity_svc = EntityService(db)
    settings_svc = SettingsService(db)

    # Get sitemap settings
    sitemap_settings = await settings_svc.get_by_category("sitemap")
    excluded_types = (
        sitemap_settings.get("exclude_types", "").split(",")
        if sitemap_settings.get("exclude_types")
        else []
    )
    excluded_urls = (
        sitemap_settings.get("exclude_urls", "").split("\n")
        if sitemap_settings.get("exclude_urls")
        else []
    )
    excluded_urls = [u.strip() for u in excluded_urls if u.strip()]

    # Get current sitemap URLs
    SEOService(entity_svc, site_url)

    # Get all URLs that would be in sitemap
    urls = []
    for ct_name in ["post", "page"]:
        if ct_name in excluded_types:
            continue

        entities = await entity_svc.find(
            ct_name,
            limit=1000,
            filters={"status": "published"} if ct_name == "post" else {},
        )

        for e in entities:
            data = entity_svc.serialize(e)
            slug = data.get("slug", e.id)
            url_path = f"/{ct_name}/{slug}"

            if url_path not in excluded_urls:
                urls.append(
                    {
                        "loc": f"{site_url}{url_path}",
                        "lastmod": e.updated_at.strftime("%Y-%m-%d") if e.updated_at else "",
                        "changefreq": "weekly" if ct_name == "post" else "monthly",
                        "priority": "0.8" if ct_name == "post" else "0.5",
                        "type": ct_name,
                    }
                )

    # Get robots.txt content
    robots_txt = f"""User-agent: *
Allow: /

# Disallow admin and API
Disallow: /admin/
Disallow: /api/

# Sitemap
Sitemap: {site_url}/sitemap.xml"""

    context = await get_context(request, db, current_user, "tools")
    context.update(
        {
            "site_url": site_url,
            "urls": urls,
            "total_urls": len(urls),
            "last_generated": None,  # Dynamic generation
            "excluded_types": excluded_types,
            "excluded_urls": excluded_urls,
            "default_changefreq": sitemap_settings.get("default_changefreq", "weekly"),
            "default_priority": sitemap_settings.get("default_priority", "0.5"),
            "robots_txt": robots_txt,
            "message": request.query_params.get("message"),
        }
    )

    return templates.TemplateResponse("admin/sitemap.html", context)


@router.post("/tools/regenerate-sitemap", response_class=HTMLResponse)
async def regenerate_sitemap(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Regenerate sitemap (clear cache if any)."""
    from ..services.cache import cache_service

    # Clear sitemap cache if exists
    cache_service.delete("sitemap:xml")

    return RedirectResponse(
        url="/admin/tools/sitemap?message=Sitemap regenerated successfully",
        status_code=303,
    )


@router.post("/tools/sitemap-exclusions", response_class=HTMLResponse)
async def save_sitemap_exclusions(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Save sitemap exclusion settings."""
    from ..services.settings import SettingsService

    settings_svc = SettingsService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)
    user_id = user_data.get("id")

    form_data = await request.form()

    # Get excluded types (multiple checkboxes)
    exclude_types = form_data.getlist("exclude_types")
    exclude_urls = form_data.get("exclude_urls", "")
    default_changefreq = form_data.get("default_changefreq", "weekly")
    default_priority = form_data.get("default_priority", "0.5")

    # Save settings
    await settings_svc.set(
        "sitemap.exclude_types", ",".join(exclude_types), category="sitemap", user_id=user_id
    )
    await settings_svc.set(
        "sitemap.exclude_urls", exclude_urls, category="sitemap", user_id=user_id
    )
    await settings_svc.set(
        "sitemap.default_changefreq", default_changefreq, category="sitemap", user_id=user_id
    )
    await settings_svc.set(
        "sitemap.default_priority", default_priority, category="sitemap", user_id=user_id
    )

    # Clear sitemap cache
    from ..services.cache import cache_service

    cache_service.delete("sitemap:xml")

    return RedirectResponse(
        url="/admin/tools/sitemap?message=Sitemap settings saved",
        status_code=303,
    )


# === Link Validator ===


@router.get("/tools/link-validator", response_class=HTMLResponse)
async def link_validator_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Link validator page."""
    require_feature("link_validator")
    context = await get_context(request, db, current_user, "tools")
    return templates.TemplateResponse("admin/link_validator.html", context)


@router.post("/tools/validate-links", response_class=HTMLResponse)
async def validate_links(
    request: Request,
    check_external: str = Form("false"),
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Run link validation."""
    require_feature("link_validator")
    from ..services.link_validator import LinkValidatorService

    site_url = str(request.base_url).rstrip("/")
    validator = LinkValidatorService(db, site_url)

    results = await validator.validate_all_links(check_external=check_external == "true")

    context = await get_context(request, db, current_user, "tools")
    context.update(
        {
            "broken_links": results["broken_links"],
            "external_errors": results["external_errors"],
            "stats": results["stats"],
        }
    )

    return templates.TemplateResponse("admin/link_validator.html", context)


@router.post("/tools/find-orphans", response_class=HTMLResponse)
async def find_orphan_pages(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Find orphan pages."""
    from ..services.link_validator import LinkValidatorService

    site_url = str(request.base_url).rstrip("/")
    validator = LinkValidatorService(db, site_url)

    orphans = await validator.find_orphan_pages()

    context = await get_context(request, db, current_user, "tools")
    context.update(
        {
            "orphans": orphans,
        }
    )

    return templates.TemplateResponse("admin/link_validator.html", context)
