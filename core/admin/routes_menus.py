"""Admin menu routes."""

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


@router.get("/menus", response_class=HTMLResponse)
async def menu_list(
    request: Request,
    location: str = "header",
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Menu management page."""
    require_feature("menu")
    from ..services.menu import MenuService

    menu_svc = MenuService(db)

    # Get menu items for the selected location with error handling
    try:
        items = await menu_svc.get_flat_menu_items(location)
        menu_tree = await menu_svc.get_menu(location)
        has_db_items = await menu_svc.has_db_menu(location)
    except Exception as e:
        logger.error("menu_list_error", location=location, error=str(e))
        items = []
        menu_tree = []
        has_db_items = False

    context = await get_context(request, db, current_user, "menus")
    context.update(
        {
            "items": items,
            "menu_tree": [m.to_dict() for m in menu_tree],
            "current_location": location,
            "locations": [
                {"value": "header", "label": "ヘッダー"},
                {"value": "footer", "label": "フッター"},
                {"value": "sidebar", "label": "サイドバー"},
            ],
            "has_db_items": has_db_items,
            "message": request.query_params.get("message"),
        }
    )

    return templates.TemplateResponse("admin/menus.html", context)


@router.post("/menus/import", response_class=HTMLResponse)
async def menu_import_yaml(
    request: Request,
    location: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Import menu items from YAML config to database."""
    require_feature("menu")
    from ..services.menu import MenuService

    menu_svc = MenuService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)

    count = await menu_svc.import_from_yaml(location, user_id=user_data.get("id"))

    return RedirectResponse(
        url=f"/admin/menus?location={location}&message={count}件のメニュー項目をインポートしました",
        status_code=303,
    )


@router.post("/menus/item", response_class=HTMLResponse)
async def menu_item_create(
    request: Request,
    location: str = Form(...),
    label: str = Form(...),
    url: str = Form("#"),
    target: str = Form("_self"),
    link_type: str = Form("custom"),
    linked_entity_id: str = Form(""),
    icon: str = Form(""),
    parent_id: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Create a new menu item."""
    require_feature("menu")
    from ..services.menu import MenuService

    menu_svc = MenuService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)

    await menu_svc.create_menu_item(
        location=location,
        label=label,
        url=url,
        target=target,
        icon=icon,
        link_type=link_type,
        linked_entity_id=linked_entity_id if linked_entity_id else None,
        parent_id=parent_id if parent_id else None,
        user_id=user_data.get("id"),
    )

    return RedirectResponse(
        url=f"/admin/menus?location={location}&message=メニュー項目を作成しました",
        status_code=303,
    )


@router.post("/menus/item/{item_id}", response_class=HTMLResponse)
async def menu_item_update(
    request: Request,
    item_id: str,
    location: str = Form(...),
    label: str = Form(...),
    url: str = Form("#"),
    target: str = Form("_self"),
    link_type: str = Form("custom"),
    linked_entity_id: str = Form(""),
    icon: str = Form(""),
    parent_id: str = Form(""),
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Update a menu item."""
    require_feature("menu")
    from ..services.menu import MenuService

    menu_svc = MenuService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)

    await menu_svc.update_menu_item(
        menu_item_id=item_id,
        data={
            "label": label,
            "url": url,
            "target": target,
            "link_type": link_type,
            "linked_entity_id": linked_entity_id,
            "icon": icon,
        },
        parent_id=parent_id if parent_id else None,
        user_id=user_data.get("id"),
    )

    return RedirectResponse(
        url=f"/admin/menus?location={location}&message=メニュー項目を更新しました",
        status_code=303,
    )


@router.delete("/menus/item/{item_id}")
async def menu_item_delete(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Delete a menu item."""
    require_feature("menu")
    from ..services.menu import MenuService

    # YAML items cannot be deleted - must import to DB first
    if item_id.startswith("yaml_"):
        return HTMLResponse(
            content="YAML設定のメニューは削除できません。先に「Import from YAML」でDBにインポートしてください。",
            status_code=400,
        )

    menu_svc = MenuService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)

    deleted = await menu_svc.delete_menu_item(item_id, user_id=user_data.get("id"))
    if not deleted:
        return HTMLResponse(
            content="メニュー項目が見つかりません。",
            status_code=404,
        )
    return HTMLResponse(content="", status_code=200)


@router.post("/menus/reorder")
async def menu_reorder(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Reorder menu items via AJAX."""
    require_feature("menu")
    from ..services.menu import MenuService

    menu_svc = MenuService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)

    body = await request.json()
    location = body.get("location", "header")
    items = body.get("items", [])

    await menu_svc.reorder_menu_items(location, items, user_id=user_data.get("id"))

    return {"status": "ok"}
