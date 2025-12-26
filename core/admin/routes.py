"""Admin routes - HTMX-powered admin interface."""

from typing import Optional

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.entity import EntityService
from ..services.auth import AuthService
from ..services.field import field_service
from ..models import Entity
from ..rate_limit import limiter


router = APIRouter(prefix="/admin", tags=["admin"])

# Templates
templates = Jinja2Templates(directory="core/templates")


async def get_current_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[Entity]:
    """Get current admin user from session."""
    token = request.cookies.get("session")
    if not token:
        return None

    auth_svc = AuthService(db)
    user = await auth_svc.get_current_user(token)

    if not user:
        return None

    # Check if user has admin role
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(user)
    if user_data.get("role") not in ("admin", "editor"):
        return None

    return user


def require_admin(request: Request, user: Optional[Entity] = Depends(get_current_admin)):
    """Require admin authentication."""
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
    return user


# Common template context
async def get_context(
    request: Request,
    db: AsyncSession,
    current_user: Optional[Entity] = None,
    current_page: str = "dashboard",
):
    """Get common template context."""
    content_types = field_service.get_all_content_types()

    entity_svc = EntityService(db)
    user_data = None
    if current_user:
        user_data = entity_svc.serialize(current_user)

    # Get CSRF token from request state (set by middleware)
    csrf_token = getattr(request.state, "csrf_token", "")

    # Get pending comment count for sidebar badge
    from ..services.comment import CommentService
    comment_svc = CommentService(db)
    pending_comment_count = await comment_svc.get_pending_count()

    return {
        "request": request,
        "content_types": content_types,
        "current_user": user_data,
        "current_page": current_page,
        "csrf_token": csrf_token,
        "pending_comment_count": pending_comment_count,
    }


# === Login ===

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page."""
    from ..services.oauth import oauth_service
    csrf_token = getattr(request.state, "csrf_token", "")
    return templates.TemplateResponse("admin/login.html", {
        "request": request,
        "error": None,
        "csrf_token": csrf_token,
        "google_oauth_enabled": oauth_service.is_configured("google"),
    })


@router.post("/login", response_class=HTMLResponse)
@limiter.limit("5/minute")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Process login."""
    from ..main import validate_csrf_token
    if not validate_csrf_token(request, csrf_token):
        return templates.TemplateResponse("admin/login.html", {
            "request": request,
            "error": "CSRFトークンが無効です。ページを再読み込みしてください。",
            "email": email,
            "csrf_token": getattr(request.state, "csrf_token", ""),
        }, status_code=403)

    auth_svc = AuthService(db)

    try:
        user, token = await auth_svc.login(
            email=email,
            password=password,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
        )

        # Check admin role
        entity_svc = EntityService(db)
        user_data = entity_svc.serialize(user)
        if user_data.get("role") not in ("admin", "editor"):
            csrf_token = getattr(request.state, "csrf_token", "")
            return templates.TemplateResponse("admin/login.html", {
                "request": request,
                "error": "Access denied. Admin role required.",
                "email": email,
                "csrf_token": csrf_token,
            })

        # Set cookie and redirect
        response = RedirectResponse(url="/admin", status_code=303)
        response.set_cookie(
            key="session",
            value=token,
            httponly=True,
            secure=False,  # Set True in production
            samesite="lax",
            max_age=86400,
        )
        return response

    except ValueError as e:
        csrf_token = getattr(request.state, "csrf_token", "")
        return templates.TemplateResponse("admin/login.html", {
            "request": request,
            "error": str(e),
            "email": email,
            "csrf_token": csrf_token,
        })


@router.get("/logout")
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Logout."""
    token = request.cookies.get("session")
    if token:
        auth_svc = AuthService(db)
        await auth_svc.logout(token)

    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie("session")
    return response


# === Dashboard ===

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Dashboard page."""
    entity_svc = EntityService(db)
    content_types = field_service.get_all_content_types()

    # Get stats for each content type
    stats = {}
    for ct_name in content_types.keys():
        stats[ct_name] = await entity_svc.count(ct_name)

    # Get recent posts
    recent_posts = []
    posts = await entity_svc.find("post", limit=5, order_by="-created_at")
    for post in posts:
        data = entity_svc.serialize(post)
        recent_posts.append(data)

    context = await get_context(request, db, current_user, "dashboard")
    context.update({
        "stats": stats,
        "recent_posts": recent_posts,
    })

    return templates.TemplateResponse("admin/dashboard.html", context)


# === Media ===

@router.get("/media", response_class=HTMLResponse)
async def media_list(
    request: Request,
    page: int = 1,
    q: str = "",
    type: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Media library page."""
    from ..services.media import MediaService
    media_svc = MediaService(db)

    per_page = 20
    offset = (page - 1) * per_page

    # Prepare filters
    mime_type = f"{type}/" if type else None
    search = q if q else None

    items = await media_svc.find(limit=per_page, offset=offset, mime_type=mime_type, search=search)
    total = await media_svc.count(mime_type=mime_type, search=search)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 0

    context = await get_context(request, db, current_user, "media")
    context.update({
        "items": [media_svc.serialize(m) for m in items],
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "message": request.query_params.get("message"),
        "search_query": q,
        "type_filter": type,
    })

    return templates.TemplateResponse("admin/media.html", context)


# === Widget Management ===

@router.get("/widgets", response_class=HTMLResponse)
async def widgets_page(
    request: Request,
    area: str = "sidebar",
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Widget management page."""
    from ..services.widget import WidgetService
    widget_svc = WidgetService(db)

    widgets = await widget_svc.get_widgets_for_area(area)
    widget_types = WidgetService.get_available_widget_types()

    areas = [
        {"value": "sidebar", "label": "サイドバー"},
        {"value": "footer_1", "label": "フッター1"},
        {"value": "footer_2", "label": "フッター2"},
        {"value": "footer_3", "label": "フッター3"},
    ]

    context = await get_context(request, db, current_user, "widgets")
    context.update({
        "widgets": widgets,
        "widget_types": widget_types,
        "current_area": area,
        "areas": areas,
        "message": request.query_params.get("message"),
    })

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
    from ..services.widget import WidgetService
    widget_svc = WidgetService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)

    body = await request.json()
    area = body.get("area", "sidebar")
    items = body.get("items", [])

    await widget_svc.reorder_widgets(area, items, user_id=user_data.get("id"))
    return {"status": "ok"}


# === Settings Management ===

@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    category: str = "site",
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Settings management page."""
    from ..services.settings import SettingsService
    settings_svc = SettingsService(db)

    # Get settings for the selected category
    settings_data = await settings_svc.get_by_category(category)

    # Define setting fields for each category
    setting_fields = {
        "site": [
            {"key": "name", "label": "サイト名", "type": "text"},
            {"key": "tagline", "label": "タグライン", "type": "text"},
            {"key": "url", "label": "サイトURL", "type": "url"},
            {"key": "language", "label": "言語", "type": "text"},
            {"key": "timezone", "label": "タイムゾーン", "type": "text"},
        ],
        "seo": [
            {"key": "title_separator", "label": "タイトル区切り", "type": "text"},
            {"key": "default_description", "label": "デフォルト説明文", "type": "textarea"},
            {"key": "default_og_image", "label": "デフォルトOG画像", "type": "text"},
        ],
        "media": [
            {"key": "max_size", "label": "最大アップロードサイズ (bytes)", "type": "number"},
            {"key": "image_max_width", "label": "画像最大幅", "type": "number"},
            {"key": "image_max_height", "label": "画像最大高さ", "type": "number"},
            {"key": "image_quality", "label": "画像品質 (1-100)", "type": "number"},
            {"key": "image_format", "label": "画像フォーマット", "type": "text"},
        ],
        "security": [
            {"key": "session_expire", "label": "セッション有効期限 (秒)", "type": "number"},
            {"key": "login_attempts", "label": "最大ログイン試行回数", "type": "number"},
            {"key": "lockout_duration", "label": "ロックアウト時間 (秒)", "type": "number"},
            {"key": "password_min_length", "label": "パスワード最小長", "type": "number"},
        ],
    }

    categories = [
        {"value": "site", "label": "サイト情報"},
        {"value": "seo", "label": "SEO"},
        {"value": "media", "label": "メディア"},
        {"value": "security", "label": "セキュリティ"},
    ]

    context = await get_context(request, db, current_user, "settings")
    context.update({
        "settings": settings_data,
        "fields": setting_fields.get(category, []),
        "current_category": category,
        "categories": categories,
        "message": request.query_params.get("message"),
    })

    return templates.TemplateResponse("admin/settings.html", context)


@router.post("/settings", response_class=HTMLResponse)
async def settings_save(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Save settings."""
    from ..services.settings import SettingsService
    settings_svc = SettingsService(db)
    entity_svc = EntityService(db)

    form_data = await request.form()
    category = form_data.get("category", "site")
    user_data = entity_svc.serialize(current_user)
    user_id = user_data.get("id")

    # Process each setting
    count = 0
    for key, value in form_data.items():
        if key in ("csrf_token", "category"):
            continue

        full_key = f"{category}.{key}"
        await settings_svc.set(full_key, value, category=category, user_id=user_id)
        count += 1

    return RedirectResponse(
        url=f"/admin/settings?category={category}&message={count}件の設定を保存しました",
        status_code=303,
    )


# === Menu Management ===

@router.get("/menus", response_class=HTMLResponse)
async def menu_list(
    request: Request,
    location: str = "header",
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Menu management page."""
    from ..services.menu import MenuService
    menu_svc = MenuService(db)

    # Get menu items for the selected location
    items = await menu_svc.get_flat_menu_items(location)
    menu_tree = await menu_svc.get_menu(location)
    has_db_items = await menu_svc.has_db_menu(location)

    context = await get_context(request, db, current_user, "menus")
    context.update({
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
    })

    return templates.TemplateResponse("admin/menus.html", context)


@router.post("/menus/import", response_class=HTMLResponse)
async def menu_import_yaml(
    request: Request,
    location: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Import menu items from YAML config to database."""
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
    from ..services.menu import MenuService
    menu_svc = MenuService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)

    await menu_svc.delete_menu_item(item_id, user_id=user_data.get("id"))
    return HTMLResponse(content="", status_code=200)


@router.post("/menus/reorder")
async def menu_reorder(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Reorder menu items via AJAX."""
    import json
    from ..services.menu import MenuService
    menu_svc = MenuService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)

    body = await request.json()
    location = body.get("location", "header")
    items = body.get("items", [])

    await menu_svc.reorder_menu_items(location, items, user_id=user_data.get("id"))

    return {"status": "ok"}


# === Comment Moderation ===

@router.get("/comments", response_class=HTMLResponse)
async def comments_list(
    request: Request,
    status: str = "pending",
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Comment moderation page."""
    from ..services.comment import CommentService
    comment_svc = CommentService(db)

    per_page = 20

    # Get comments with status filter
    comments = await comment_svc.get_recent_comments(
        limit=per_page,
        status=status if status != "all" else None,
    )

    # Get counts for each status
    pending_count = await comment_svc.get_pending_count()

    status_options = [
        {"value": "pending", "label": f"承認待ち ({pending_count})"},
        {"value": "approved", "label": "承認済み"},
        {"value": "rejected", "label": "拒否"},
        {"value": "spam", "label": "スパム"},
        {"value": "all", "label": "すべて"},
    ]

    context = await get_context(request, db, current_user, "comments")
    context.update({
        "comments": comments,
        "current_status": status,
        "status_options": status_options,
        "pending_count": pending_count,
        "message": request.query_params.get("message"),
    })

    return templates.TemplateResponse("admin/comments.html", context)


@router.post("/comments/{comment_id}/moderate", response_class=HTMLResponse)
async def comment_moderate(
    request: Request,
    comment_id: str,
    action: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Moderate a comment (approve, reject, spam)."""
    from ..services.comment import CommentService
    comment_svc = CommentService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)

    success = await comment_svc.moderate(
        comment_id=comment_id,
        action=action,
        user_id=user_data.get("id"),
    )

    action_msg = {
        "approve": "承認しました",
        "reject": "拒否しました",
        "spam": "スパムとしてマークしました",
    }.get(action, "更新しました")

    return RedirectResponse(
        url=f"/admin/comments?message=コメントを{action_msg}" if success else "/admin/comments?message=操作に失敗しました",
        status_code=303,
    )


@router.post("/comments/bulk", response_class=HTMLResponse)
async def comments_bulk_action(
    request: Request,
    ids: str = Form(...),
    action: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Perform bulk action on comments."""
    from ..services.comment import CommentService
    comment_svc = CommentService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)
    user_id = user_data.get("id")

    comment_ids = [cid.strip() for cid in ids.split(",") if cid.strip()]
    if not comment_ids:
        return RedirectResponse(
            url="/admin/comments?message=コメントが選択されていません",
            status_code=303,
        )

    count = 0
    for comment_id in comment_ids:
        if action == "delete":
            if await comment_svc.delete_comment(comment_id, user_id=user_id):
                count += 1
        elif action in ("approve", "reject", "spam"):
            if await comment_svc.moderate(comment_id, action, user_id=user_id):
                count += 1

    action_msg = {
        "delete": "削除",
        "approve": "承認",
        "reject": "拒否",
        "spam": "スパム",
    }.get(action, "更新")

    return RedirectResponse(
        url=f"/admin/comments?message={count}件のコメントを{action_msg}しました",
        status_code=303,
    )


@router.delete("/comments/{comment_id}")
async def comment_delete(
    comment_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Delete a comment."""
    from ..services.comment import CommentService
    comment_svc = CommentService(db)
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)

    await comment_svc.delete_comment(comment_id, user_id=user_data.get("id"))
    return HTMLResponse(content="", status_code=200)


# === Entity List ===

@router.get("/{type_name}", response_class=HTMLResponse)
async def entity_list(
    request: Request,
    type_name: str,
    page: int = 1,
    q: str = "",
    status: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Entity list page."""
    content_type = field_service.get_content_type(type_name)
    if not content_type:
        raise HTTPException(status_code=404, detail="Content type not found")

    entity_svc = EntityService(db)
    per_page = 20
    offset = (page - 1) * per_page

    # Build filters
    filters = {}
    if status:
        filters["status"] = status

    # Get entities with filters
    entities_raw = await entity_svc.find(
        type_name,
        limit=per_page,
        offset=offset,
        order_by="-created_at",
        filters=filters,
    )

    # Apply text search (simple in-memory filtering for now)
    if q:
        q_lower = q.lower()
        filtered = []
        for e in entities_raw:
            data = entity_svc.serialize(e)
            # Search in text fields
            for field in content_type.fields:
                if field.type in ("string", "text", "slug"):
                    val = data.get(field.name, "")
                    if val and q_lower in str(val).lower():
                        filtered.append(e)
                        break
        entities_raw = filtered

    entities = [entity_svc.serialize(e) for e in entities_raw]

    # Get total count with filters
    from ..services.entity import QueryParams
    params = QueryParams(filters=filters)
    total = await entity_svc.count(type_name, params)
    total_pages = (total + per_page - 1) // per_page

    # Get list fields (first 3-4 important fields)
    list_fields = []
    for field in content_type.fields[:4]:
        if field.name not in ("password", "body", "blocks"):
            list_fields.append(field)

    context = await get_context(request, db, current_user, type_name)
    context.update({
        "type_name": type_name,
        "content_type": content_type,
        "entities": entities,
        "list_fields": list_fields,
        "page": page,
        "total_pages": total_pages,
        "message": request.query_params.get("message"),
        "search_query": q,
        "status_filter": status,
    })

    return templates.TemplateResponse("admin/entity_list.html", context)


# === Entity Create ===

@router.get("/{type_name}/new", response_class=HTMLResponse)
async def entity_new(
    request: Request,
    type_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """New entity form."""
    content_type = field_service.get_content_type(type_name)
    if not content_type:
        raise HTTPException(status_code=404, detail="Content type not found")

    # Get relations for this content type
    relations = await _get_relation_options(type_name, None, db)

    context = await get_context(request, db, current_user, type_name)
    context.update({
        "type_name": type_name,
        "content_type": content_type,
        "entity": None,
        "relations": relations,
    })

    return templates.TemplateResponse("admin/entity_form.html", context)


@router.post("/{type_name}", response_class=HTMLResponse)
async def entity_create(
    request: Request,
    type_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Create entity."""
    content_type = field_service.get_content_type(type_name)
    if not content_type:
        raise HTTPException(status_code=404, detail="Content type not found")

    entity_svc = EntityService(db)
    form_data = await request.form()

    # Build entity data from form
    import json as json_module
    data = {}
    for field in content_type.fields:
        value = form_data.get(field.name)
        if value is not None and value != "":
            # Type conversion
            if field.type in ("number", "integer"):
                data[field.name] = int(value)
            elif field.type == "float":
                data[field.name] = float(value)
            elif field.type == "boolean":
                data[field.name] = value == "true"
            elif field.type in ("blocks", "json", "multiselect"):
                try:
                    data[field.name] = json_module.loads(value)
                except (json_module.JSONDecodeError, TypeError):
                    data[field.name] = value
            else:
                data[field.name] = value

    try:
        user_data = entity_svc.serialize(current_user)
        entity = await entity_svc.create(type_name, data, user_id=user_data.get("id"))

        # Handle relations
        from ..services.relation import RelationService
        relation_svc = RelationService(db)

        for rel in content_type.relations:
            rel_field = f"rel_{rel.type}"
            rel_values = form_data.getlist(rel_field)
            # Filter out empty values
            rel_ids = [v for v in rel_values if v]
            if rel_ids:
                await relation_svc.sync(entity.id, rel_ids, rel.type)

        return RedirectResponse(
            url=f"/admin/{type_name}?message=Created+successfully",
            status_code=303,
        )

    except ValueError as e:
        relations = await _get_relation_options(type_name, None, db)
        context = await get_context(request, db, current_user, type_name)
        context.update({
            "type_name": type_name,
            "content_type": content_type,
            "entity": data,
            "relations": relations,
            "error": str(e),
        })
        return templates.TemplateResponse("admin/entity_form.html", context)


# === Entity Edit ===

@router.get("/{type_name}/{entity_id}/edit", response_class=HTMLResponse)
async def entity_edit(
    request: Request,
    type_name: str,
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Edit entity form."""
    content_type = field_service.get_content_type(type_name)
    if not content_type:
        raise HTTPException(status_code=404, detail="Content type not found")

    entity_svc = EntityService(db)
    entity_raw = await entity_svc.get(entity_id)
    if not entity_raw or entity_raw.type != type_name:
        raise HTTPException(status_code=404, detail="Entity not found")

    entity = entity_svc.serialize(entity_raw)
    relations = await _get_relation_options(type_name, entity_id, db)

    context = await get_context(request, db, current_user, type_name)
    context.update({
        "type_name": type_name,
        "content_type": content_type,
        "entity": entity,
        "relations": relations,
        "message": request.query_params.get("message"),
    })

    return templates.TemplateResponse("admin/entity_form.html", context)


@router.post("/{type_name}/{entity_id}", response_class=HTMLResponse)
async def entity_update(
    request: Request,
    type_name: str,
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Update entity."""
    content_type = field_service.get_content_type(type_name)
    if not content_type:
        raise HTTPException(status_code=404, detail="Content type not found")

    entity_svc = EntityService(db)
    entity_raw = await entity_svc.get(entity_id)
    if not entity_raw or entity_raw.type != type_name:
        raise HTTPException(status_code=404, detail="Entity not found")

    form_data = await request.form()

    # Build entity data from form
    import json as json_module
    data = {}
    for field in content_type.fields:
        value = form_data.get(field.name)
        if value is not None and value != "":
            # Type conversion
            if field.type in ("number", "integer"):
                data[field.name] = int(value)
            elif field.type == "float":
                data[field.name] = float(value)
            elif field.type == "boolean":
                data[field.name] = value == "true"
            elif field.type in ("blocks", "json", "multiselect"):
                try:
                    data[field.name] = json_module.loads(value)
                except (json_module.JSONDecodeError, TypeError):
                    data[field.name] = value
            else:
                data[field.name] = value
        elif field.type == "boolean":
            # Unchecked checkbox
            data[field.name] = False

    try:
        user_data = entity_svc.serialize(current_user)
        await entity_svc.update(entity_id, data, user_id=user_data.get("id"))

        # Handle relations
        from ..services.relation import RelationService
        relation_svc = RelationService(db)

        for rel in content_type.relations:
            rel_field = f"rel_{rel.type}"
            rel_values = form_data.getlist(rel_field)
            # Filter out empty values
            rel_ids = [v for v in rel_values if v]
            # Sync relations (empty list = remove all)
            await relation_svc.sync(entity_id, rel_ids, rel.type)

        return RedirectResponse(
            url=f"/admin/{type_name}/{entity_id}/edit?message=Updated+successfully",
            status_code=303,
        )

    except ValueError as e:
        entity = entity_svc.serialize(entity_raw)
        entity.update(data)  # Show submitted values
        relations = await _get_relation_options(type_name, entity_id, db)

        context = await get_context(request, db, current_user, type_name)
        context.update({
            "type_name": type_name,
            "content_type": content_type,
            "entity": entity,
            "relations": relations,
            "error": str(e),
        })
        return templates.TemplateResponse("admin/entity_form.html", context)


# === Entity Delete ===

@router.delete("/{type_name}/{entity_id}")
async def entity_delete(
    type_name: str,
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Delete entity (soft delete)."""
    entity_svc = EntityService(db)
    entity = await entity_svc.get(entity_id)
    if not entity or entity.type != type_name:
        raise HTTPException(status_code=404, detail="Entity not found")

    user_data = entity_svc.serialize(current_user)
    await entity_svc.delete(entity_id, user_id=user_data.get("id"))

    # Return empty response for HTMX to remove the row
    return HTMLResponse(content="", status_code=200)


# === Bulk Actions ===

@router.post("/{type_name}/bulk")
async def entity_bulk_action(
    request: Request,
    type_name: str,
    ids: str = Form(...),
    action: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Perform bulk action on entities."""
    content_type = field_service.get_content_type(type_name)
    if not content_type:
        raise HTTPException(status_code=404, detail="Content type not found")

    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(current_user)
    user_id = user_data.get("id")

    entity_ids = [eid.strip() for eid in ids.split(",") if eid.strip()]
    if not entity_ids:
        raise HTTPException(status_code=400, detail="No entities selected")

    count = 0
    for entity_id in entity_ids:
        entity = await entity_svc.get(entity_id)
        if not entity or entity.type != type_name:
            continue

        if action == "delete":
            await entity_svc.delete(entity_id, user_id=user_id)
            count += 1
        elif action in ("publish", "draft", "archive"):
            status_map = {
                "publish": "published",
                "draft": "draft",
                "archive": "archived",
            }
            await entity_svc.update(entity_id, {"status": status_map[action]}, user_id=user_id)
            count += 1

    action_msg = {
        "delete": "deleted",
        "publish": "published",
        "draft": "set to draft",
        "archive": "archived",
    }.get(action, "updated")

    return RedirectResponse(
        url=f"/admin/{type_name}?message={count}+items+{action_msg}",
        status_code=303,
    )


# === Helper Functions ===

async def _get_relation_options(
    type_name: str,
    entity_id: Optional[str],
    db: AsyncSession,
) -> list:
    """Get relation options for entity form."""
    content_type = field_service.get_content_type(type_name)
    if not content_type or not content_type.relations:
        return []

    entity_svc = EntityService(db)
    from ..services.relation import RelationService
    relation_svc = RelationService(db)

    relations = []
    for rel in content_type.relations:
        rel_def = field_service.get_relation_type(rel.type)
        if not rel_def:
            continue

        # Get target entities
        target_type = rel_def.to_type
        target_entities = await entity_svc.find(target_type, limit=100)

        # Get current relations if editing
        current_ids = set()
        if entity_id:
            current_related = await relation_svc.get_related(entity_id, rel.type)
            current_ids = {e.id for e in current_related}

        options = []
        for target in target_entities:
            target_data = entity_svc.serialize(target)
            label = target_data.get("name") or target_data.get("title") or target.id[:8]
            options.append({
                "id": target.id,
                "label": label,
                "selected": target.id in current_ids,
            })

        relations.append({
            "name": rel.type,
            "label": rel_def.label if rel_def.label else rel.type,
            "multiple": rel_def.type in ("many_to_many", "one_to_many"),
            "options": options,
        })

    return relations
