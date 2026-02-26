"""Admin widget routes."""

import structlog

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Entity
from ..services.entity import EntityService
from ..utils import require_feature
from .helpers import templates, require_admin, get_context

logger = structlog.get_logger()

router = APIRouter()


@router.get("/widgets", response_class=HTMLResponse)
async def widgets_page(
    request: Request,
    area: str = "sidebar",
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Widget management page."""
    require_feature("widget")
    from ..services.widget import WidgetService

    widget_svc = WidgetService(db)

    # Get widgets with error handling
    try:
        widgets = await widget_svc.get_widgets_for_area(area)
    except Exception as e:
        logger.error("widgets_page_error", area=area, error=str(e))
        widgets = []

    widget_types = WidgetService.get_available_widget_types()

    areas = [
        {"value": "sidebar", "label": "サイドバー"},
        {"value": "footer_1", "label": "フッター1"},
        {"value": "footer_2", "label": "フッター2"},
        {"value": "footer_3", "label": "フッター3"},
    ]

    context = await get_context(request, db, current_user, "widgets")
    context.update(
        {
            "widgets": widgets,
            "widget_types": widget_types,
            "current_area": area,
            "areas": areas,
            "message": request.query_params.get("message"),
        }
    )

    return templates.TemplateResponse("admin/widgets.html", context)


@router.post("/widgets", response_class=HTMLResponse)
async def widget_create(
    request: Request,
    area: str = Form(...),
    widget_type: str = Form(...),
    title: str = Form(""),
    custom_html: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Create a new widget."""
    require_feature("widget")
    from ..services.widget import WidgetService

    widget_svc = WidgetService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)

    await widget_svc.create_widget(
        widget_type=widget_type,
        area=area,
        title=title,
        custom_html=custom_html,
        user_id=user_data.get("id"),
    )

    return RedirectResponse(
        url=f"/admin/widgets?area={area}&message=ウィジェットを作成しました",
        status_code=303,
    )


@router.post("/widgets/{widget_id}", response_class=HTMLResponse)
async def widget_update(
    request: Request,
    widget_id: str,
    area: str = Form(...),
    widget_type: str = Form(...),
    title: str = Form(""),
    custom_html: str = Form(""),
    is_active: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Update a widget."""
    require_feature("widget")
    from ..services.widget import WidgetService

    widget_svc = WidgetService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)

    await widget_svc.update_widget(
        widget_id,
        {
            "title": title,
            "widget_type": widget_type,
            "custom_html": custom_html,
            "is_active": is_active == "true",
        },
        user_id=user_data.get("id"),
    )

    return RedirectResponse(
        url=f"/admin/widgets?area={area}&message=ウィジェットを更新しました",
        status_code=303,
    )


@router.delete("/widgets/{widget_id}")
async def widget_delete(
    widget_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Delete a widget."""
    require_feature("widget")
    from ..services.widget import WidgetService

    widget_svc = WidgetService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)

    await widget_svc.delete_widget(widget_id, user_id=user_data.get("id"))
    return HTMLResponse(content="", status_code=200)


@router.post("/widgets/reorder")
async def widgets_reorder(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Reorder widgets."""
    require_feature("widget")
    from ..services.widget import WidgetService

    widget_svc = WidgetService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)

    body = await request.json()
    area = body.get("area", "sidebar")
    items = body.get("items", [])

    await widget_svc.reorder_widgets(area, items, user_id=user_data.get("id"))
    return {"status": "ok"}
