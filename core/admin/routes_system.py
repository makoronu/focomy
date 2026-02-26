"""Admin system routes - updates, preview, backup."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Entity
from ..services.entity import EntityService
from .helpers import templates, require_admin, require_admin_api, get_context

router = APIRouter()


# === Update Check ===


@router.get("/api/update-check")
async def check_for_updates(
    request: Request,
    current_user: Entity = Depends(require_admin),
    force: bool = False,
):
    """Check for Focomy updates - returns HTML for HTMX."""
    from ..services.update import update_service

    update_info = await update_service.check_for_updates(force=force)

    if update_info.has_update:
        html = f'''<span class="badge bg-warning text-dark">
            新バージョン {update_info.latest_version} が利用可能です
            <a href="{update_info.release_url}" target="_blank" class="ms-1">詳細</a>
        </span>'''
    else:
        ver = update_info.current_version
        html = f'<span class="badge bg-success">最新バージョン ({ver})</span>'

    return HTMLResponse(content=html)


@router.post("/api/update-execute")
async def execute_update(
    request: Request,
    current_user: Entity = Depends(require_admin),
):
    """Execute Focomy update via pip - returns HTML for HTMX."""
    from ..services.update import update_service

    result = await update_service.execute_update()

    if result.success:
        html = f'''<div class="alert alert-success mb-0">
            <strong>{result.message}</strong>
            <p class="mb-0 mt-2 small">数秒後にページを更新してください。</p>
        </div>'''
    else:
        html = f'''<div class="alert alert-danger mb-0">
            <strong>エラー:</strong> {result.message}
        </div>'''

    return HTMLResponse(content=html)


@router.post("/api/preview/render")
async def preview_render(
    request: Request,
    current_user: Entity = Depends(require_admin_api),
):
    """Render Editor.js blocks to HTML for preview."""
    from ..services.theme import theme_service

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    content = body.get("content", {})
    html = theme_service.render_blocks_html(content)

    return {"html": html}


@router.post("/api/preview/token")
async def create_preview_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin_api),
):
    """Create a preview token for an entity."""
    from ..services.preview import get_preview_service

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    entity_id = body.get("entity_id")
    if not entity_id:
        raise HTTPException(status_code=400, detail="entity_id required")

    # Verify entity exists
    entity_svc = EntityService(db)
    entity = await entity_svc.get(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Create preview token
    preview_svc = get_preview_service(db)
    token = await preview_svc.create_token(entity_id, current_user.id)
    preview_url = preview_svc.get_preview_url(token)

    return {"token": token, "url": preview_url}


@router.get("/system", response_class=HTMLResponse)
async def system_info(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """System information page."""
    import platform
    import sys

    from ..services.update import update_service

    context = await get_context(request, db, current_user, "system")
    update_info = await update_service.check_for_updates()

    context["system"] = {
        "python_version": sys.version,
        "platform": platform.platform(),
        "focomy_version": update_info.current_version,
        "latest_version": update_info.latest_version,
        "has_update": update_info.has_update,
        "release_url": update_info.release_url,
    }

    return templates.TemplateResponse("admin/system.html", context)


# === Backup ===


@router.get("/backup", response_class=HTMLResponse)
async def backup_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Backup management page."""
    from datetime import datetime as dt

    from ..config import get_settings

    context = await get_context(request, db, current_user, "backup")
    settings = get_settings()
    backups_dir = settings.base_dir / "backups"

    backups = []
    if backups_dir.exists():
        for f in sorted(backups_dir.glob("*.zip"), reverse=True):
            stat = f.stat()
            backups.append({
                "name": f.name,
                "size": stat.st_size,
                "created": dt.fromtimestamp(stat.st_mtime),
            })

    context.update({
        "backups": backups[:20],  # Show last 20 backups
        "backups_dir": str(backups_dir),
    })
    return templates.TemplateResponse("admin/backup.html", context)


@router.get("/backup/download/{filename}")
async def download_backup(
    filename: str,
    current_user: Entity = Depends(require_admin),
):
    """Download a backup file."""
    from fastapi.responses import FileResponse

    from ..config import get_settings

    settings = get_settings()
    backups_dir = settings.base_dir / "backups"
    file_path = backups_dir / filename

    # Security: prevent path traversal
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Backup not found")

    return FileResponse(
        file_path,
        filename=filename,
        media_type="application/zip",
    )
