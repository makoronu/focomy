"""Admin theme routes - theme management and customization."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Entity
from ..services.entity import EntityService
from .helpers import templates, require_admin, require_admin_api, get_context

router = APIRouter()


# === Theme Management ===


@router.get("/themes", response_class=HTMLResponse)
async def themes_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Theme management page."""
    from ..services.settings import SettingsService
    from ..services.theme import theme_service

    themes_data = []
    for _name, theme in theme_service.get_all_themes().items():
        themes_data.append(
            {
                "name": theme.name,
                "label": theme.label,
                "description": theme.description,
                "version": theme.version,
                "author": theme.author,
                "preview": getattr(theme, "preview", None),
            }
        )

    # Get active theme from database settings
    settings_svc = SettingsService(db)
    theme_settings = await settings_svc.get_by_category("theme")
    active_theme = theme_settings.get("active", "default")

    context = await get_context(request, db, current_user, "themes")
    context.update(
        {
            "themes": themes_data,
            "active_theme": active_theme,
            "message": request.query_params.get("message"),
        }
    )

    return templates.TemplateResponse("admin/themes.html", context)


@router.post("/themes/{theme_name}/activate", response_class=HTMLResponse)
async def activate_theme(
    request: Request,
    theme_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Activate a theme."""
    from ..services.settings import SettingsService
    from ..services.theme import theme_service

    # Validate theme exists
    themes = theme_service.get_all_themes()
    if theme_name not in themes:
        raise HTTPException(status_code=404, detail="Theme not found")

    # Save to settings
    settings_svc = SettingsService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)
    await settings_svc.set(
        "theme.active", theme_name, category="theme", user_id=user_data.get("id")
    )

    # Update theme service
    theme_service.set_current_theme(theme_name)

    return RedirectResponse(url="/admin/themes?message=テーマを変更しました", status_code=303)


# === Theme Customization ===


@router.get("/themes/{theme_name}/customize", response_class=HTMLResponse)
async def customize_theme_page(
    request: Request,
    theme_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Theme customization page."""
    from ..services.theme import theme_service

    # Validate theme exists
    theme = theme_service.get_theme(theme_name)
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")

    # Get customizable settings
    settings = theme_service.get_customizable_settings(theme_name)

    # Group settings by category
    grouped_settings = {}
    for setting in settings:
        category = setting.get("category", "other")
        if category not in grouped_settings:
            grouped_settings[category] = []
        grouped_settings[category].append(setting)

    # Debug log
    import structlog
    logger = structlog.get_logger()
    logger.info(
        "customize_theme_page",
        theme_name=theme_name,
        settings_count=len(settings),
        grouped_keys=list(grouped_settings.keys()),
        colors_count=len(grouped_settings.get("colors", [])),
    )

    context = await get_context(request, db, current_user, "themes")
    context.update({
        "theme": {
            "name": theme.name,
            "label": theme.label,
        },
        "settings": settings,
        "grouped_settings": grouped_settings,
        "message": request.query_params.get("message"),
    })

    return templates.TemplateResponse("admin/customize.html", context)


@router.get("/api/theme/settings")
async def get_theme_settings(
    request: Request,
    theme_name: str = None,
    current_user: Entity = Depends(require_admin_api),
):
    """Get theme customization settings."""
    from ..services.settings import SettingsService
    from ..services.theme import theme_service

    # Get active theme if not specified
    if not theme_name:
        db = request.state.db
        settings_svc = SettingsService(db)
        theme_settings = await settings_svc.get_by_category("theme")
        theme_name = theme_settings.get("active", "default")

    theme = theme_service.get_theme(theme_name)
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")

    settings = theme_service.get_customizable_settings(theme_name)
    customizations = theme_service.get_customizations(theme_name)

    return {
        "theme_name": theme_name,
        "settings": settings,
        "customizations": customizations,
    }


@router.post("/api/theme/settings")
async def save_theme_settings(
    request: Request,
    current_user: Entity = Depends(require_admin_api),
):
    """Save theme customization settings."""
    from ..services.theme import theme_service

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    theme_name = body.get("theme_name")
    values = body.get("values", {})

    if not theme_name:
        raise HTTPException(status_code=400, detail="theme_name is required")

    theme = theme_service.get_theme(theme_name)
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")

    success = theme_service.set_customizations(values, theme_name)

    if success:
        return {"success": True, "message": "カスタマイズを保存しました"}
    else:
        raise HTTPException(status_code=500, detail="Failed to save customizations")


@router.post("/api/theme/preview-css")
async def preview_theme_css(
    request: Request,
    current_user: Entity = Depends(require_admin_api),
):
    """Generate preview CSS with temporary values."""
    from fastapi.responses import PlainTextResponse

    from ..services.theme import theme_service

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    theme_name = body.get("theme_name")
    preview_values = body.get("values", {})

    theme = theme_service.get_theme(theme_name)
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")

    css = theme_service.generate_preview_css(preview_values, theme_name)

    return PlainTextResponse(content=css, media_type="text/css")
