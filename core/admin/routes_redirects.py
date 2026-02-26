"""Admin redirect routes."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Entity
from ..services.entity import EntityService
from .helpers import templates, require_admin, get_context

router = APIRouter()


# === Redirect Management ===


@router.get("/redirects", response_class=HTMLResponse)
async def redirects_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Redirect management page."""
    from ..services.redirect import RedirectService

    redirect_svc = RedirectService(db)

    redirects = await redirect_svc.get_all_redirects(include_inactive=True)

    context = await get_context(request, db, current_user, "redirects")
    context.update(
        {
            "redirects": redirects,
            "message": request.query_params.get("message"),
        }
    )

    return templates.TemplateResponse("admin/redirects.html", context)


@router.post("/redirects", response_class=HTMLResponse)
async def redirect_create(
    request: Request,
    from_path: str = Form(...),
    to_path: str = Form(...),
    status_code: str = Form("301"),
    match_type: str = Form("exact"),
    preserve_query: str = Form(""),
    is_active: str = Form(""),
    notes: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Create a new redirect."""
    from ..services.redirect import RedirectService

    redirect_svc = RedirectService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)

    try:
        await redirect_svc.create_redirect(
            from_path=from_path,
            to_path=to_path,
            status_code=int(status_code),
            match_type=match_type,
            preserve_query=preserve_query == "true",
            notes=notes,
            user_id=user_data.get("id"),
        )

        return RedirectResponse(
            url="/admin/redirects?message=Redirect created successfully",
            status_code=303,
        )
    except ValueError as e:
        return RedirectResponse(
            url=f"/admin/redirects?message=Error: {str(e)}",
            status_code=303,
        )


@router.post("/redirects/{redirect_id}", response_class=HTMLResponse)
async def redirect_update(
    request: Request,
    redirect_id: str,
    from_path: str = Form(...),
    to_path: str = Form(...),
    status_code: str = Form("301"),
    match_type: str = Form("exact"),
    preserve_query: str = Form(""),
    is_active: str = Form(""),
    notes: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Update a redirect."""
    from ..services.redirect import RedirectService

    redirect_svc = RedirectService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)

    await redirect_svc.update_redirect(
        redirect_id,
        {
            "from_path": from_path,
            "to_path": to_path,
            "status_code": status_code,
            "match_type": match_type,
            "preserve_query": preserve_query == "true",
            "is_active": is_active == "true",
            "notes": notes,
        },
        user_id=user_data.get("id"),
    )

    return RedirectResponse(
        url="/admin/redirects?message=Redirect updated successfully",
        status_code=303,
    )


@router.post("/redirects/{redirect_id}/toggle")
async def redirect_toggle(
    redirect_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Toggle redirect active status."""
    from ..services.redirect import RedirectService

    redirect_svc = RedirectService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)

    result = await redirect_svc.toggle_active(redirect_id, user_id=user_data.get("id"))
    if result:
        return {"status": "ok", "is_active": result.get("is_active")}
    return {"status": "error"}


@router.delete("/redirects/{redirect_id}")
async def redirect_delete(
    redirect_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Delete a redirect."""
    from ..services.redirect import RedirectService

    redirect_svc = RedirectService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)

    await redirect_svc.delete_redirect(redirect_id, user_id=user_data.get("id"))
    return HTMLResponse(content="", status_code=200)


@router.get("/redirects/test")
async def redirect_test(
    request: Request,
    path: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Test a path against redirect rules."""
    from ..services.redirect import RedirectService

    redirect_svc = RedirectService(db)

    result = await redirect_svc.test_redirect(path)
    if result:
        return {
            "match": True,
            "to_path": result["to_path"],
            "status_code": result["status_code"],
        }
    return {"match": False}
