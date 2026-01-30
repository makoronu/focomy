"""Admin routes - HTMX-powered admin interface."""

from pathlib import Path

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import get_db
from ..models import Entity
from ..rate_limit import limiter
from ..services.audit import AuditService, get_client_ip, get_request_id
from ..services.auth import AuthService
from ..services.entity import EntityService
from ..services.field import field_service
from ..services.rbac import Permission, RBACService
from ..schemas.import_schema import (
    ConnectionTestRequest,
    ConnectionTestResponse,
    ErrorResponse,
)
from ..utils import require_feature
from .url import AdminURL

import json as json_module
from typing import Any

router = APIRouter(prefix="/admin", tags=["admin"])

# Templates - パッケージ内の絶対パスを使用（PyPIパッケージ対応）
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# Add version to template globals
from .. import __version__
templates.env.globals["version"] = __version__

# Add AdminURL helper to template globals
templates.env.globals["AdminURL"] = AdminURL


def parse_form_fields(fields: list, form_data: dict) -> dict[str, Any]:
    """Parse form data based on field definitions.

    Converts form values to appropriate Python types based on field.type.
    Handles: number, integer, float, boolean, blocks, json, multiselect.
    """
    data = {}
    for field in fields:
        value = form_data.get(field.name)
        if value is not None and value != "":
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
    return data


async def get_current_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Entity | None:
    """Get current admin user from session."""
    token = request.cookies.get("session")
    if not token:
        return None

    auth_svc = AuthService(db)
    user = await auth_svc.get_current_user(token)

    if not user:
        return None

    # Check if user has any role (author, editor, admin can all access admin panel)
    # RBAC will control what they can do
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(user)
    if user_data.get("role") not in ("admin", "editor", "author"):
        return None

    return user


def require_admin(request: Request, user: Entity | None = Depends(get_current_admin)):
    """Require admin authentication."""
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})
    return user


def require_admin_api(request: Request, user: Entity | None = Depends(get_current_admin)):
    """Require admin authentication for API endpoints (returns 401, not redirect)."""
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


async def check_permission(
    db: AsyncSession,
    user: Entity,
    content_type: str,
    permission: Permission,
    entity_id: str | None = None,
) -> None:
    """Check if user has permission. Raises HTTPException if denied."""
    entity_svc = EntityService(db)
    user_data = entity_svc.serialize(user)
    user_data.get("role", "author")

    rbac_svc = RBACService(db)
    result = await rbac_svc.can_access(
        user_id=user_data.get("id"),
        content_type=content_type,
        permission=permission,
        entity_id=entity_id,
    )

    if not result.allowed:
        raise HTTPException(status_code=403, detail=result.reason or "Permission denied")


# Common template context
async def get_context(
    request: Request,
    db: AsyncSession,
    current_user: Entity | None = None,
    current_page: str = "dashboard",
):
    """Get common template context."""
    all_content_types = field_service.get_all_content_types()

    entity_svc = EntityService(db)
    user_data = None
    user_role = "admin"
    if current_user:
        user_data = entity_svc.serialize(current_user)
        user_role = user_data.get("role", "author")

    # Filter content types based on role and convert to dict for template
    rbac_svc = RBACService(db)
    if user_role == "admin":
        # Convert Pydantic models to dicts for Jinja2 compatibility
        content_types = {name: ct.model_dump() for name, ct in all_content_types.items()}
    else:
        visible_type_names = rbac_svc.get_menu_items(
            user_role, [ct.name for ct in all_content_types.values()]
        )
        content_types = {
            name: ct.model_dump()
            for name, ct in all_content_types.items()
            if ct.name in visible_type_names
        }

    # Get CSRF token from request state (set by middleware)
    csrf_token = getattr(request.state, "csrf_token", "")

    # Get pending comment count for sidebar badge
    from ..services.comment import CommentService

    comment_svc = CommentService(db)
    pending_comment_count = await comment_svc.get_pending_count()

    # Get channels for sidebar
    channels = []
    try:
        channels_raw = await entity_svc.find("channel", limit=50, order_by="sort_order")
        channels = [entity_svc.serialize(c) for c in channels_raw]
    except Exception as e:
        # Channel content type may not exist yet - log but continue
        import logging
        logging.debug(f"Channel content type not available: {e}")

    # Get orphan posts count (posts without channel)
    orphan_post_count = 0
    try:
        from ..services.relation import RelationService
        relation_svc = RelationService(db)
        all_posts = await entity_svc.find("post", limit=1000)
        for post in all_posts:
            related_channels = await relation_svc.get_related(post.id, "post_channel")
            if not related_channels:
                orphan_post_count += 1
    except Exception:
        pass  # Post content type may not exist

    # Get active theme for customize link
    from ..services.settings import SettingsService
    settings_svc = SettingsService(db)
    theme_settings = await settings_svc.get_by_category("theme")
    active_theme = theme_settings.get("active", "default")

    return {
        "request": request,
        "content_types": content_types,
        "current_user": user_data,
        "current_page": current_page,
        "csrf_token": csrf_token,
        "pending_comment_count": pending_comment_count,
        "user_role": user_role,
        "channels": channels,
        "orphan_post_count": orphan_post_count,
        "active_theme": active_theme,
    }


# === Login ===


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page."""
    from ..services.oauth import oauth_service

    csrf_token = getattr(request.state, "csrf_token", "")
    return templates.TemplateResponse(
        "admin/login.html",
        {
            "request": request,
            "error": None,
            "csrf_token": csrf_token,
            "google_oauth_enabled": oauth_service.is_configured("google"),
        },
    )


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
        return templates.TemplateResponse(
            "admin/login.html",
            {
                "request": request,
                "error": "CSRFトークンが無効です。ページを再読み込みしてください。",
                "email": email,
                "csrf_token": getattr(request.state, "csrf_token", ""),
            },
            status_code=403,
        )

    auth_svc = AuthService(db)

    try:
        user, token = await auth_svc.login(
            email=email,
            password=password,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
        )

        # Check if user has valid role (author, editor, admin can all access)
        entity_svc = EntityService(db)
        user_data = entity_svc.serialize(user)
        if user_data.get("role") not in ("admin", "editor", "author"):
            # Log failed login attempt
            audit_svc = AuditService(db)
            await audit_svc.log_login(
                user_id=user_data.get("id"),
                user_email=email,
                user_name=user_data.get("name"),
                success=False,
                ip_address=get_client_ip(request),
                user_agent=request.headers.get("User-Agent"),
                request_id=get_request_id(request),
                failure_reason="Valid role required",
            )
            csrf_token = getattr(request.state, "csrf_token", "")
            return templates.TemplateResponse(
                "admin/login.html",
                {
                    "request": request,
                    "error": "Access denied. No valid role assigned.",
                    "email": email,
                    "csrf_token": csrf_token,
                },
            )

        # Log successful login
        audit_svc = AuditService(db)
        await audit_svc.log_login(
            user_id=user_data.get("id"),
            user_email=email,
            user_name=user_data.get("name"),
            success=True,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            request_id=get_request_id(request),
        )

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
        # Log failed login attempt
        audit_svc = AuditService(db)
        await audit_svc.log_login(
            user_id=None,
            user_email=email,
            success=False,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            request_id=get_request_id(request),
            failure_reason=str(e),
        )
        csrf_token = getattr(request.state, "csrf_token", "")
        return templates.TemplateResponse(
            "admin/login.html",
            {
                "request": request,
                "error": str(e),
                "email": email,
                "csrf_token": csrf_token,
            },
        )


@router.get("/logout")
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Logout."""
    token = request.cookies.get("session")
    if token:
        auth_svc = AuthService(db)
        user = await auth_svc.get_current_user(token)

        # Log logout
        if user:
            entity_svc = EntityService(db)
            user_data = entity_svc.serialize(user)
            audit_svc = AuditService(db)
            await audit_svc.log_logout(
                user_id=user_data.get("id"),
                user_email=user_data.get("email"),
                user_name=user_data.get("name"),
                ip_address=get_client_ip(request),
                user_agent=request.headers.get("User-Agent"),
                request_id=get_request_id(request),
            )

        await auth_svc.logout(token)

    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie("session")
    return response


# === Password Reset ===


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    """Forgot password page."""
    csrf_token = getattr(request.state, "csrf_token", "")
    return templates.TemplateResponse(
        "admin/forgot_password.html",
        {
            "request": request,
            "csrf_token": csrf_token,
            "message": None,
            "error": None,
        },
    )


@router.post("/forgot-password", response_class=HTMLResponse)
@limiter.limit("3/minute")
async def forgot_password_submit(
    request: Request,
    email: str = Form(...),
    csrf_token: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Process forgot password request."""
    from ..config import settings
    from ..main import validate_csrf_token
    from ..services.mail import EmailMessage, mail_service

    if not validate_csrf_token(request, csrf_token):
        return templates.TemplateResponse(
            "admin/forgot_password.html",
            {
                "request": request,
                "error": "CSRFトークンが無効です。ページを再読み込みしてください。",
                "message": None,
                "csrf_token": getattr(request.state, "csrf_token", ""),
            },
            status_code=403,
        )

    auth_svc = AuthService(db)
    reset_token = await auth_svc.request_password_reset(email)

    # Always show success message (security: don't reveal if email exists)
    message = "パスワードリセットのメールを送信しました。メールをご確認ください。"

    # Send email if token was generated (email exists)
    if reset_token:
        reset_url = f"{settings.site.url}/admin/reset-password?token={reset_token}"

        mail_service.send(
            EmailMessage(
                to=email,
                subject="[Focomy] パスワードリセット",
                body=f"""パスワードリセットのリクエストを受け付けました。

以下のリンクをクリックして、新しいパスワードを設定してください。
このリンクは1時間有効です。

{reset_url}

このリクエストに心当たりがない場合は、このメールを無視してください。
""",
                html=f"""
<p>パスワードリセットのリクエストを受け付けました。</p>
<p>以下のボタンをクリックして、新しいパスワードを設定してください。<br>
このリンクは1時間有効です。</p>
<p><a href="{reset_url}" style="display: inline-block; padding: 10px 20px; background: #3b82f6; color: white; text-decoration: none; border-radius: 5px;">パスワードをリセット</a></p>
<p>このリクエストに心当たりがない場合は、このメールを無視してください。</p>
""",
            )
        )

    return templates.TemplateResponse(
        "admin/forgot_password.html",
        {
            "request": request,
            "message": message,
            "error": None,
            "csrf_token": getattr(request.state, "csrf_token", ""),
        },
    )


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(
    request: Request,
    token: str = "",
):
    """Reset password page."""
    if not token:
        return RedirectResponse(url="/admin/forgot-password", status_code=303)

    csrf_token = getattr(request.state, "csrf_token", "")
    return templates.TemplateResponse(
        "admin/reset_password.html",
        {
            "request": request,
            "token": token,
            "csrf_token": csrf_token,
            "error": None,
        },
    )


@router.post("/reset-password", response_class=HTMLResponse)
async def reset_password_submit(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    csrf_token: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """Process password reset."""
    from ..main import validate_csrf_token

    if not validate_csrf_token(request, csrf_token):
        return templates.TemplateResponse(
            "admin/reset_password.html",
            {
                "request": request,
                "token": token,
                "error": "CSRFトークンが無効です。ページを再読み込みしてください。",
                "csrf_token": getattr(request.state, "csrf_token", ""),
            },
            status_code=403,
        )

    if password != password_confirm:
        return templates.TemplateResponse(
            "admin/reset_password.html",
            {
                "request": request,
                "token": token,
                "error": "パスワードが一致しません。",
                "csrf_token": getattr(request.state, "csrf_token", ""),
            },
        )

    auth_svc = AuthService(db)

    try:
        success = await auth_svc.reset_password(token, password)

        if success:
            return templates.TemplateResponse(
                "admin/login.html",
                {
                    "request": request,
                    "error": None,
                    "message": "パスワードをリセットしました。新しいパスワードでログインしてください。",
                    "csrf_token": getattr(request.state, "csrf_token", ""),
                    "google_oauth_enabled": False,
                },
            )
        else:
            return templates.TemplateResponse(
                "admin/reset_password.html",
                {
                    "request": request,
                    "token": token,
                    "error": "リセットトークンが無効または期限切れです。",
                    "csrf_token": getattr(request.state, "csrf_token", ""),
                },
            )

    except ValueError as e:
        return templates.TemplateResponse(
            "admin/reset_password.html",
            {
                "request": request,
                "token": token,
                "error": str(e),
                "csrf_token": getattr(request.state, "csrf_token", ""),
            },
        )


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

    # Get recent posts with channel info
    from ..services.relation import RelationService

    relation_svc = RelationService(db)
    recent_posts = []
    posts = await entity_svc.find("post", limit=5, order_by="-created_at")
    for post in posts:
        data = entity_svc.serialize(post)
        # Get channel for this post
        related_channels = await relation_svc.get_related(post.id, "post_channel")
        if related_channels:
            channel_data = entity_svc.serialize(related_channels[0])
            data["channel_slug"] = channel_data.get("slug")
            data["channel_title"] = channel_data.get("title")
        recent_posts.append(data)

    # Check for updates
    from ..services.update import update_service

    update_info = await update_service.check_for_updates()

    context = await get_context(request, db, current_user, "dashboard")
    context.update(
        {
            "stats": stats,
            "recent_posts": recent_posts,
            "update_info": {
                "current_version": update_info.current_version,
                "latest_version": update_info.latest_version,
                "has_update": update_info.has_update,
                "release_url": update_info.release_url,
            },
        }
    )

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
    require_feature("media")
    from ..services.media import MediaService

    media_svc = MediaService(db)

    per_page = get_settings().admin.per_page
    offset = (page - 1) * per_page

    # Prepare filters
    mime_type = f"{type}/" if type else None
    search = q if q else None

    items = await media_svc.find(limit=per_page, offset=offset, mime_type=mime_type, search=search)
    total = await media_svc.count(mime_type=mime_type, search=search)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 0

    context = await get_context(request, db, current_user, "media")
    context.update(
        {
            "items": [media_svc.serialize(m) for m in items],
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "message": request.query_params.get("message"),
            "search_query": q,
            "type_filter": type,
        }
    )

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
            {
                "key": "title_separator",
                "label": "タイトル区切り",
                "type": "text",
                "placeholder": " | ",
            },
            {"key": "default_description", "label": "デフォルト説明文", "type": "textarea"},
            {"key": "default_og_image", "label": "デフォルトOG画像URL", "type": "url"},
            {"key": "og_site_name", "label": "OGサイト名", "type": "text"},
            {"key": "og_locale", "label": "OGロケール", "type": "text", "placeholder": "ja_JP"},
            {
                "key": "twitter_site",
                "label": "Twitter @ユーザー名",
                "type": "text",
                "placeholder": "@example",
            },
            {
                "key": "ga4_id",
                "label": "Google Analytics 4 ID",
                "type": "text",
                "placeholder": "G-XXXXXXXXXX",
            },
            {
                "key": "gtm_id",
                "label": "Google Tag Manager ID",
                "type": "text",
                "placeholder": "GTM-XXXXXXX",
            },
            {"key": "search_console_id", "label": "Search Console 認証メタ", "type": "text"},
            {"key": "bing_webmaster_id", "label": "Bing Webmaster 認証メタ", "type": "text"},
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
        "headers": [
            {
                "key": "info",
                "label": "セキュリティヘッダー情報",
                "type": "info",
                "value": "以下のセキュリティヘッダーが自動的に適用されています",
            },
            {
                "key": "hsts",
                "label": "HSTS (HTTP Strict Transport Security)",
                "type": "readonly",
                "value": "有効 (本番環境のみ)",
            },
            {"key": "csp", "label": "Content-Security-Policy", "type": "readonly", "value": "有効"},
            {
                "key": "x_frame_options",
                "label": "X-Frame-Options",
                "type": "readonly",
                "value": "SAMEORIGIN",
            },
            {
                "key": "x_content_type",
                "label": "X-Content-Type-Options",
                "type": "readonly",
                "value": "nosniff",
            },
            {
                "key": "referrer_policy",
                "label": "Referrer-Policy",
                "type": "readonly",
                "value": "strict-origin-when-cross-origin",
            },
            {
                "key": "permissions_policy",
                "label": "Permissions-Policy",
                "type": "readonly",
                "value": "有効 (不要なAPIを無効化)",
            },
            {
                "key": "coop",
                "label": "Cross-Origin-Opener-Policy",
                "type": "readonly",
                "value": "same-origin",
            },
            {
                "key": "corp",
                "label": "Cross-Origin-Resource-Policy",
                "type": "readonly",
                "value": "same-origin",
            },
        ],
    }

    categories = [
        {"value": "site", "label": "サイト情報"},
        {"value": "seo", "label": "SEO"},
        {"value": "media", "label": "メディア"},
        {"value": "security", "label": "セキュリティ"},
        {"value": "headers", "label": "セキュリティヘッダー"},
    ]

    context = await get_context(request, db, current_user, "settings")
    context.update(
        {
            "settings": settings_data,
            "fields": setting_fields.get(category, []),
            "current_category": category,
            "categories": categories,
            "message": request.query_params.get("message"),
        }
    )

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

    per_page = get_settings().admin.per_page

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
    context.update(
        {
            "comments": comments,
            "current_status": status,
            "status_options": status_options,
            "pending_count": pending_count,
            "message": request.query_params.get("message"),
        }
    )

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
        url=(
            f"/admin/comments?message=コメントを{action_msg}"
            if success
            else "/admin/comments?message=操作に失敗しました"
        ),
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


# === WordPress Import ===


@router.get("/import", response_class=HTMLResponse)
async def import_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """WordPress import page."""
    require_feature("wordpress_import")
    context = await get_context(request, db, current_user, "import")
    return templates.TemplateResponse("admin/import.html", context)


@router.post(
    "/import/test-connection",
    response_model=ConnectionTestResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("10/minute")
async def test_wp_connection(
    request: Request,
    data: ConnectionTestRequest,
    current_user: Entity = Depends(require_admin),
):
    """Test WordPress REST API connection."""
    require_feature("wordpress_import")
    from ..services.wordpress_import import RESTClientConfig, WordPressRESTClient

    request_id = str(uuid.uuid4())[:8]

    try:
        config = RESTClientConfig(
            site_url=str(data.url),
            username=data.username,
            password=data.password,
        )

        async with WordPressRESTClient(config) as client:
            result = await client.test_connection()

            return ConnectionTestResponse(
                success=result.success,
                message=result.message,
                site_name=result.site_name,
                authenticated=result.authenticated,
                errors=result.errors,
            )

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="CONNECTION_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/analyze",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def analyze_import(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Analyze WordPress data for import."""
    require_feature("wordpress_import")
    import tempfile
    from pathlib import Path

    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        form = await request.form()
        source_type = form.get("source_type", "wxr")

        # Validate source_type
        if source_type not in ("wxr", "rest"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error="Invalid source_type. Must be 'wxr' or 'rest'",
                    code="INVALID_SOURCE_TYPE",
                    request_id=request_id,
                ).model_dump(),
            )

        import_svc = WordPressImportService(db)

        # Determine upload directory and base URL
        upload_dir = Path("uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)
        base_url = str(request.base_url).rstrip("/")

        # Validate webp_quality
        try:
            webp_quality = int(form.get("webp_quality", "85"))
            if not 1 <= webp_quality <= 100:
                webp_quality = 85
        except ValueError:
            webp_quality = 85

        config = {
            "import_media": form.get("import_media") == "true",
            "download_media": form.get("download_media") == "true",
            "convert_to_webp": form.get("convert_to_webp") == "true",
            "webp_quality": webp_quality,
            "include_drafts": form.get("include_drafts") == "true",
            "import_comments": form.get("import_comments") == "true",
            "import_menus": form.get("import_menus") == "true",
            "upload_dir": str(upload_dir),
            "base_url": base_url,
        }

        source_url = None
        source_file = None

        if source_type == "wxr":
            # Handle file upload
            file = form.get("file")
            if not file:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=ErrorResponse(
                        error="No file uploaded",
                        code="NO_FILE",
                        request_id=request_id,
                    ).model_dump(),
                )

            # Save to temp file
            temp_dir = Path(tempfile.gettempdir())
            temp_file = temp_dir / f"wp_import_{file.filename}"
            content = await file.read()
            temp_file.write_bytes(content)
            source_file = str(temp_file)

        else:
            # REST API
            source_url = form.get("url")
            config["username"] = form.get("username", "")
            config["password"] = form.get("password", "")

            if not source_url:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content=ErrorResponse(
                        error="URL is required for REST API import",
                        code="URL_REQUIRED",
                        request_id=request_id,
                    ).model_dump(),
                )

        # Create job
        entity_svc = EntityService(db)
        user_data = entity_svc.serialize(current_user)

        job = await import_svc.create_job(
            source_type=source_type,
            source_url=source_url,
            source_file=source_file,
            config=config,
            user_id=user_data.get("id"),
        )

        # Run analysis
        analysis = await import_svc.analyze(job.id)

        if not analysis:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=ErrorResponse(
                    error="Analysis failed",
                    code="ANALYSIS_FAILED",
                    request_id=request_id,
                ).model_dump(),
            )

        return {
            "success": True,
            "job_id": job.id,
            "analysis": analysis,
            "request_id": request_id,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/{job_id}/dry-run",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def dry_run_import(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Run a dry-run simulation of the import without making changes."""
    require_feature("wordpress_import")
    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)
        job = await import_svc.get_job(job_id)

        if not job:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error="Job not found",
                    code="JOB_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        # Run dry-run
        result = await import_svc.dry_run(job_id)

        if not result:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=ErrorResponse(
                    error="Dry-run failed",
                    code="DRY_RUN_FAILED",
                    request_id=request_id,
                ).model_dump(),
            )

        # Convert to JS-expected format
        summary = result.get("summary", {})
        counts = {
            "new": sum(s.get("new", 0) for s in summary.values()),
            "skip": sum(s.get("duplicates", 0) for s in summary.values()),
            "error": len(result.get("errors", [])),
            "update": 0,
        }
        # Build items with status for each type
        items = {}
        for entity_type, stats in summary.items():
            items[entity_type] = [
                {"status": "new"} for _ in range(stats.get("new", 0))
            ] + [
                {"status": "skip"} for _ in range(stats.get("duplicates", 0))
            ]

        return {
            "success": True,
            "job_id": job_id,
            "counts": counts,
            "items": items,
            "warnings": result.get("warnings", []),
            "errors": result.get("errors", []),
            "duplicates": result.get("duplicates", []),
            "has_errors": len(result.get("errors", [])) > 0,
            "request_id": request_id,
        }

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/{job_id}/preview",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def preview_import(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Preview import by creating a small number of sample items."""
    require_feature("wordpress_import")
    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)
        job = await import_svc.get_job(job_id)

        if not job:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error="Job not found",
                    code="JOB_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        result = await import_svc.preview_import(job_id, limit=3)

        if not result or not result.get("success"):
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=ErrorResponse(
                    error=result.get("error", "Preview failed") if result else "Preview failed",
                    code="PREVIEW_FAILED",
                    request_id=request_id,
                ).model_dump(),
            )

        return {
            "success": True,
            "job_id": job_id,
            "preview": result,
            "request_id": request_id,
        }

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/{job_id}/preview/confirm",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def confirm_preview(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Confirm preview items and finalize them."""
    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)
        result = await import_svc.confirm_preview(job_id)

        if not result or not result.get("success"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error=result.get("error", "Confirm failed") if result else "Confirm failed",
                    code="CONFIRM_FAILED",
                    request_id=request_id,
                ).model_dump(),
            )

        return {
            "success": True,
            "confirmed": result.get("confirmed", 0),
            "request_id": request_id,
        }

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/{job_id}/preview/discard",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def discard_preview(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Discard preview items and delete them."""
    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)
        result = await import_svc.discard_preview(job_id)

        if not result or not result.get("success"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error=result.get("error", "Discard failed") if result else "Discard failed",
                    code="DISCARD_FAILED",
                    request_id=request_id,
                ).model_dump(),
            )

        return {
            "success": True,
            "discarded": result.get("discarded", 0),
            "request_id": request_id,
        }

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/{job_id}/resume",
    responses={
        400: {"model": ErrorResponse, "description": "Cannot resume job"},
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("3/minute")
async def resume_import(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Resume a failed or cancelled import job from checkpoint."""
    require_feature("wordpress_import")
    import asyncio

    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)
        job = await import_svc.get_job(job_id)

        if not job:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error="Import job not found",
                    code="JOB_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        # Check if job can be resumed
        from ..models import ImportJobStatus

        if job.status not in (
            ImportJobStatus.FAILED,
            ImportJobStatus.CANCELLED,
        ):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error=f"Cannot resume job with status: {job.status}. Only failed or cancelled jobs can be resumed.",
                    code="INVALID_STATUS",
                    request_id=request_id,
                ).model_dump(),
            )

        # Get checkpoint info
        checkpoint = job.checkpoint or {}
        last_phase = checkpoint.get("last_phase", "beginning")

        # Start resume in background
        asyncio.create_task(import_svc.resume_import(job_id))

        return {
            "success": True,
            "job_id": job_id,
            "message": f"Import resumed from phase: {last_phase}",
            "checkpoint": {
                "last_phase": last_phase,
                "authors_processed": len(checkpoint.get("authors", [])),
                "categories_processed": len(checkpoint.get("categories", [])),
                "tags_processed": len(checkpoint.get("tags", [])),
                "media_processed": len(checkpoint.get("media", [])),
                "posts_processed": len(checkpoint.get("posts", [])),
                "pages_processed": len(checkpoint.get("pages", [])),
                "menus_processed": len(checkpoint.get("menus", [])),
            },
            "request_id": request_id,
        }

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/{job_id}/detect-diff",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def detect_diff(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Detect differences between WordPress and database."""
    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)
        result = await import_svc.detect_diff(job_id)

        if not result:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error="Import job not found",
                    code="JOB_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        if not result.get("success"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error=result.get("error", "Diff detection failed"),
                    code="DIFF_FAILED",
                    request_id=request_id,
                ).model_dump(),
            )

        return {
            **result,
            "request_id": request_id,
        }

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/{job_id}/import-diff",
    responses={
        400: {"model": ErrorResponse, "description": "No diff result found"},
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("3/minute")
async def import_diff(
    request: Request,
    job_id: str,
    import_new: bool = True,
    import_updated: bool = True,
    delete_removed: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Import only the differences (new and updated items)."""
    require_feature("wordpress_import")
    import asyncio

    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)
        job = await import_svc.get_job(job_id)

        if not job:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error="Import job not found",
                    code="JOB_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        # Start diff import in background
        asyncio.create_task(
            import_svc.import_diff(
                job_id,
                import_new=import_new,
                import_updated=import_updated,
                delete_removed=delete_removed,
            )
        )

        return {
            "success": True,
            "job_id": job_id,
            "message": "Diff import started",
            "options": {
                "import_new": import_new,
                "import_updated": import_updated,
                "delete_removed": delete_removed,
            },
            "request_id": request_id,
        }

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.get(
    "/import/{job_id}/rollback-status",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def get_rollback_status(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Get rollback status for an import job."""
    from ..services.wordpress_import.rollback import RollbackService

    request_id = str(uuid.uuid4())[:8]

    try:
        rollback_svc = RollbackService(db)
        result = await rollback_svc.get_rollback_status(job_id)

        if not result.get("success"):
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error=result.get("error", "Job not found"),
                    code="JOB_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        return {
            **result,
            "request_id": request_id,
        }

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/{job_id}/rollback",
    responses={
        400: {"model": ErrorResponse, "description": "Rollback not allowed"},
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("1/minute")
async def rollback_import(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Rollback an import job - deletes all imported entities."""
    require_feature("wordpress_import")
    from ..services.wordpress_import.rollback import RollbackService

    request_id = str(uuid.uuid4())[:8]

    try:
        rollback_svc = RollbackService(db)

        # Check if rollback is allowed
        can_rollback = await rollback_svc.can_rollback(job_id)
        if not can_rollback.get("can_rollback"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error=can_rollback.get("reason", "Rollback not allowed"),
                    code="ROLLBACK_NOT_ALLOWED",
                    request_id=request_id,
                ).model_dump(),
            )

        # Perform rollback
        result = await rollback_svc.rollback(job_id)

        if not result.get("success"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error=result.get("error", "Rollback failed"),
                    code="ROLLBACK_FAILED",
                    request_id=request_id,
                ).model_dump(),
            )

        return {
            **result,
            "request_id": request_id,
        }

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/{job_id}/fix-links",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("3/minute")
async def fix_import_links(
    request: Request,
    job_id: str,
    source_domain: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Fix internal links in imported content."""
    require_feature("wordpress_import")
    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)

        # Check job exists
        job = await import_svc.get_job(job_id)
        if not job:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error="Job not found",
                    code="JOB_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        # Fix links
        result = await import_svc.fix_links(job_id, source_domain)

        return {
            **result,
            "request_id": request_id,
        }

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/{job_id}/dry-run",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def dry_run_import(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Run dry run simulation for import job."""
    require_feature("wordpress_import")
    from pathlib import Path

    from ..services.wordpress_import import WordPressImportService
    from ..services.wordpress_import.dry_run import DryRunService
    from ..services.wordpress_import.wxr_parser import WXRParser

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)

        # Check job exists
        job = await import_svc.get_job(job_id)
        if not job:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error="Job not found",
                    code="JOB_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        # Parse WXR file
        if not job.source_file:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error="No source file found",
                    code="NO_SOURCE_FILE",
                    request_id=request_id,
                ).model_dump(),
            )

        file_path = Path(job.source_file)
        if not file_path.exists():
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error="Source file not found",
                    code="FILE_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        # Parse and run dry run
        parser = WXRParser()
        wxr_data = parser.parse(str(file_path))

        dry_run_svc = DryRunService(db)
        result = await dry_run_svc.run(job_id, wxr_data)

        return {
            "success": True,
            **result.to_dict(),
            "request_id": request_id,
        }

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/{job_id}/preview",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def preview_import(
    request: Request,
    job_id: str,
    count: int = 3,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Run preview import with a few items."""
    require_feature("wordpress_import")
    from pathlib import Path

    from ..services.wordpress_import import WordPressImportService
    from ..services.wordpress_import.preview import PreviewService, store_preview_entities
    from ..services.wordpress_import.wxr_parser import WXRParser

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)

        # Check job exists
        job = await import_svc.get_job(job_id)
        if not job:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error="Job not found",
                    code="JOB_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        # Parse WXR file
        if not job.source_file:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error="No source file found",
                    code="NO_SOURCE_FILE",
                    request_id=request_id,
                ).model_dump(),
            )

        file_path = Path(job.source_file)
        if not file_path.exists():
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=ErrorResponse(
                    error="Source file not found",
                    code="FILE_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        # Parse and run preview
        parser = WXRParser()
        wxr_data = parser.parse(str(file_path))

        preview_svc = PreviewService(db)
        result = await preview_svc.run_preview(job_id, wxr_data, count)

        # Store preview entities for later commit/rollback
        entity_ids = [i.entity_id for i in result.items if i.entity_id]
        store_preview_entities(result.preview_id, entity_ids)

        return {
            "success": True,
            **result.to_dict(),
            "request_id": request_id,
        }

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/preview/{preview_id}/commit",
    responses={
        404: {"model": ErrorResponse, "description": "Preview not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def commit_preview(
    request: Request,
    preview_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Commit preview - keep imported items."""
    from ..services.wordpress_import.preview import (
        get_preview_entities,
        clear_preview_entities,
    )

    request_id = str(uuid.uuid4())[:8]

    try:
        entity_ids = get_preview_entities(preview_id)

        if not entity_ids:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error="Preview not found or already processed",
                    code="PREVIEW_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        # Remove preview flag from entities
        for entity_id in entity_ids:
            result = await db.execute(
                select(EntityValue).where(
                    EntityValue.entity_id == entity_id,
                    EntityValue.field_name == "preview",
                )
            )
            ev = result.scalar_one_or_none()
            if ev:
                await db.delete(ev)

        await db.commit()
        clear_preview_entities(preview_id)

        return {
            "success": True,
            "preview_id": preview_id,
            "committed_count": len(entity_ids),
            "request_id": request_id,
        }

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/preview/{preview_id}/rollback",
    responses={
        404: {"model": ErrorResponse, "description": "Preview not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def rollback_preview(
    request: Request,
    preview_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Rollback preview - delete imported items."""
    from ..utils import utcnow
    from ..services.wordpress_import.preview import (
        get_preview_entities,
        clear_preview_entities,
    )

    request_id = str(uuid.uuid4())[:8]

    try:
        entity_ids = get_preview_entities(preview_id)

        if not entity_ids:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error="Preview not found or already processed",
                    code="PREVIEW_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        # Soft delete preview entities
        deleted_count = 0
        for entity_id in entity_ids:
            result = await db.execute(
                select(Entity).where(Entity.id == entity_id)
            )
            entity = result.scalar_one_or_none()
            if entity:
                entity.deleted_at = utcnow()
                deleted_count += 1

        await db.commit()
        clear_preview_entities(preview_id)

        return {
            "success": True,
            "preview_id": preview_id,
            "rolled_back_count": deleted_count,
            "request_id": request_id,
        }

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.get(
    "/import/{job_id}/verify",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("5/minute")
async def verify_import(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Verify import integrity and generate report."""
    require_feature("wordpress_import")
    from ..services.wordpress_import.verification import VerificationService

    request_id = str(uuid.uuid4())[:8]

    try:
        service = VerificationService(db)
        report = await service.verify(job_id)

        return {
            "success": True,
            "job_id": report.job_id,
            "generated_at": report.generated_at.isoformat(),
            "counts": report.counts,
            "summary": report.summary,
            "issues": [
                {
                    "level": i.level,
                    "category": i.category,
                    "entity_type": i.entity_type,
                    "entity_id": i.entity_id,
                    "message": i.message,
                    "details": i.details,
                }
                for i in report.issues
            ],
            "has_errors": report.has_errors,
            "request_id": request_id,
        }

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/{job_id}/generate-redirects",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("3/minute")
async def generate_import_redirects(
    request: Request,
    job_id: str,
    source_url: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Generate URL redirects for imported content."""
    require_feature("wordpress_import")
    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)

        # Check job exists
        job = await import_svc.get_job(job_id)
        if not job:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error="Job not found",
                    code="JOB_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        # Generate redirects
        result = await import_svc.generate_redirects(job_id, source_url)

        return {
            **result,
            "request_id": request_id,
        }

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/{job_id}/start",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("3/minute")
async def start_import(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Start WordPress import job."""
    require_feature("wordpress_import")
    import asyncio

    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)
        job = await import_svc.get_job(job_id)

        if not job:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error="Job not found",
                    code="JOB_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        # Start import in background
        asyncio.create_task(_run_import_background(job_id))

        return {"success": True, "job_id": job_id, "request_id": request_id}

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


async def _run_import_background(job_id: str):
    """Run import in background."""
    from ..database import async_session
    from ..services.wordpress_import import WordPressImportService

    async with async_session() as db:
        import_svc = WordPressImportService(db)
        await import_svc.run_import(job_id)


@router.get(
    "/import/{job_id}/status",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
async def get_import_status(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Get import job status for polling."""
    require_feature("wordpress_import")
    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)
        job = await import_svc.get_job(job_id)

        if not job:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content=ErrorResponse(
                    error="Job not found",
                    code="JOB_NOT_FOUND",
                    request_id=request_id,
                ).model_dump(),
            )

        return job.to_dict()

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


@router.post(
    "/import/{job_id}/cancel",
    responses={
        500: {"model": ErrorResponse, "description": "Server error"},
    },
)
@limiter.limit("10/minute")
async def cancel_import(
    request: Request,
    job_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Cancel import job."""
    require_feature("wordpress_import")
    from ..services.wordpress_import import WordPressImportService

    request_id = str(uuid.uuid4())[:8]

    try:
        import_svc = WordPressImportService(db)
        success = await import_svc.cancel_job(job_id)

        return {"success": success, "request_id": request_id}

    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=str(e),
                code="INTERNAL_ERROR",
                request_id=request_id,
            ).model_dump(),
        )


# === Channel Posts ===


@router.get("/channel/{channel_slug}/posts", response_class=HTMLResponse)
async def channel_posts(
    request: Request,
    channel_slug: str,
    page: int = 1,
    q: str = "",
    status_filter: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
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

    # Get posts related to this channel
    content_type = field_service.get_content_type("post")
    if not content_type:
        raise HTTPException(status_code=404, detail="Post content type not found")

    per_page = get_settings().admin.per_page
    offset = (page - 1) * per_page

    # Get all posts and filter by channel relation
    filters = {}
    if status_filter:
        filters["status"] = status_filter

    all_posts = await entity_svc.find(
        "post",
        limit=1000,
        order_by="-created_at",
        filters=filters,
    )

    # Filter by channel relation
    channel_posts = []
    for post in all_posts:
        related_channels = await relation_svc.get_related(post.id, "post_channel")
        if any(c.id == channel.id for c in related_channels):
            channel_posts.append(post)

    # Apply text search
    if q:
        q_lower = q.lower()
        filtered = []
        for post in channel_posts:
            data = entity_svc.serialize(post)
            if data.get("title") and q_lower in str(data["title"]).lower():
                filtered.append(post)
            elif data.get("body") and q_lower in str(data.get("body", "")).lower():
                filtered.append(post)
        channel_posts = filtered

    # Pagination
    total = len(channel_posts)
    total_pages = (total + per_page - 1) // per_page
    paginated_posts = channel_posts[offset : offset + per_page]

    entities = [entity_svc.serialize(p) for p in paginated_posts]

    # Get list fields (first 3-4 important fields)
    list_fields = []
    for field in content_type.fields[:4]:
        if field.name not in ("password", "body", "blocks"):
            list_fields.append(field)

    context = await get_context(request, db, current_user, "post")
    context.update(
        {
            "type_name": "post",
            "content_type": content_type.model_dump(),
            "entities": entities,
            "list_fields": [f.model_dump() for f in list_fields],
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "message": request.query_params.get("message"),
            "search_query": q,
            "status_filter": status_filter,
            "channel": channel_data,
            "channel_slug": channel_slug,
            "is_channel_view": True,
        }
    )

    return templates.TemplateResponse("admin/entity_list.html", context)


@router.get("/posts/orphan", response_class=HTMLResponse)
async def orphan_posts(
    request: Request,
    page: int = 1,
    q: str = "",
    status_filter: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """List posts without channel assignment."""
    entity_svc = EntityService(db)
    from ..services.relation import RelationService

    relation_svc = RelationService(db)

    content_type = field_service.get_content_type("post")
    if not content_type:
        raise HTTPException(status_code=404, detail="Post content type not found")

    per_page = get_settings().admin.per_page
    offset = (page - 1) * per_page

    # Get all posts and filter those without channel
    filters = {}
    if status_filter:
        filters["status"] = status_filter

    all_posts = await entity_svc.find(
        "post",
        limit=1000,
        order_by="-created_at",
        filters=filters,
    )

    # Filter posts without channel relation
    orphan_posts_list = []
    for post in all_posts:
        related_channels = await relation_svc.get_related(post.id, "post_channel")
        if not related_channels:
            orphan_posts_list.append(post)

    # Apply text search
    if q:
        q_lower = q.lower()
        filtered = []
        for post in orphan_posts_list:
            data = entity_svc.serialize(post)
            if data.get("title") and q_lower in str(data["title"]).lower():
                filtered.append(post)
            elif data.get("body") and q_lower in str(data.get("body", "")).lower():
                filtered.append(post)
        orphan_posts_list = filtered

    # Pagination
    total = len(orphan_posts_list)
    total_pages = (total + per_page - 1) // per_page
    paginated_posts = orphan_posts_list[offset : offset + per_page]

    entities = [entity_svc.serialize(p) for p in paginated_posts]

    # Get list fields
    list_fields = []
    for field in content_type.fields[:4]:
        if field.name not in ("password", "body", "blocks"):
            list_fields.append(field)

    context = await get_context(request, db, current_user, "post")
    context.update(
        {
            "type_name": "post",
            "content_type": content_type.model_dump(),
            "entities": entities,
            "list_fields": [f.model_dump() for f in list_fields],
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "message": request.query_params.get("message"),
            "search_query": q,
            "status_filter": status_filter,
            "is_orphan_view": True,
        }
    )

    return templates.TemplateResponse("admin/entity_list.html", context)


@router.get("/channel/{channel_slug}/posts/new", response_class=HTMLResponse)
async def channel_post_new(
    request: Request,
    channel_slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """New post form with channel pre-selected."""
    entity_svc = EntityService(db)

    # Get channel by slug
    channels = await entity_svc.find("channel", limit=1, filters={"slug": channel_slug})
    if not channels:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel = channels[0]
    channel_data = entity_svc.serialize(channel)

    content_type = field_service.get_content_type("post")
    if not content_type:
        raise HTTPException(status_code=404, detail="Post content type not found")

    # Get relations for this content type
    relations = await _get_relation_options("post", None, db)

    # Pre-select the channel in relations
    for rel in relations:
        if rel["name"] == "post_channel":
            for opt in rel["options"]:
                opt["selected"] = opt["id"] == channel.id

    context = await get_context(request, db, current_user, "post")
    context.update(
        {
            "type_name": "post",
            "content_type": content_type.model_dump(),
            "entity": None,
            "relations": relations,
            "channel": channel_data,
            "channel_slug": channel_slug,
            "is_channel_view": True,
            "form_action": AdminURL.entity_form_action("post", None, channel_slug),
            "cancel_url": AdminURL.entity_list("post", channel_slug),
        }
    )

    return templates.TemplateResponse("admin/entity_form.html", context)


@router.post("/channel/{channel_slug}/posts", response_class=HTMLResponse)
async def channel_post_create(
    request: Request,
    channel_slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Create post in channel."""
    entity_svc = EntityService(db)

    # Get channel by slug
    channels = await entity_svc.find("channel", limit=1, filters={"slug": channel_slug})
    if not channels:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel = channels[0]

    content_type = field_service.get_content_type("post")
    if not content_type:
        raise HTTPException(status_code=404, detail="Post content type not found")

    # RBAC permission check
    await check_permission(db, current_user, "post", Permission.CREATE)

    form_data = await request.form()

    # Build entity data from form
    data = parse_form_fields(content_type.fields, form_data)

    try:
        entity = await entity_svc.create("post", data, user_id=current_user.id)

        # Save relations - ensure channel is linked
        from ..services.relation import RelationService

        relation_svc = RelationService(db)

        for rel in content_type.relations:
            if rel.type == "post_channel":
                # Always link to channel
                await relation_svc.sync(entity.id, [channel.id], rel.type)
            else:
                rel_ids = form_data.getlist(rel.type)
                if rel_ids:
                    await relation_svc.sync(entity.id, rel_ids, rel.type)

        # Audit log
        if hasattr(request.app.state, "settings") and request.app.state.settings.audit_enabled:
            audit_svc = AuditService(db)
            await audit_svc.log(
                action="create",
                entity_type="post",
                entity_id=entity.id,
                user_id=current_user.id,
                after_data=data,
                ip_address=get_client_ip(request),
                request_id=get_request_id(request),
            )

        return RedirectResponse(
            url=f"/admin/channel/{channel_slug}/posts?message=Created+successfully",
            status_code=303,
        )

    except ValueError as e:
        channel_data = entity_svc.serialize(channel)
        relations = await _get_relation_options("post", None, db)
        context = await get_context(request, db, current_user, "post")
        context.update(
            {
                "type_name": "post",
                "content_type": content_type.model_dump(),
                "entity": data,
                "relations": relations,
                "error": str(e),
                "channel": channel_data,
                "channel_slug": channel_slug,
                "is_channel_view": True,
                "form_action": AdminURL.entity_form_action("post", None, channel_slug),
                "cancel_url": AdminURL.entity_list("post", channel_slug),
            }
        )
        return templates.TemplateResponse("admin/entity_form.html", context)


@router.get("/channel/{channel_slug}/posts/{entity_id}/edit", response_class=HTMLResponse)
async def channel_post_edit(
    request: Request,
    channel_slug: str,
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Edit post in channel."""
    entity_svc = EntityService(db)

    # Get channel by slug
    channels = await entity_svc.find("channel", limit=1, filters={"slug": channel_slug})
    if not channels:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel = channels[0]
    channel_data = entity_svc.serialize(channel)

    # Get entity
    entity = await entity_svc.get(entity_id)
    if not entity or entity.type != "post":
        raise HTTPException(status_code=404, detail="Post not found")

    content_type = field_service.get_content_type("post")
    if not content_type:
        raise HTTPException(status_code=404, detail="Post content type not found")

    entity_data = entity_svc.serialize(entity)
    relations = await _get_relation_options("post", entity_id, db)

    context = await get_context(request, db, current_user, "post")
    context.update(
        {
            "type_name": "post",
            "content_type": content_type.model_dump(),
            "entity": entity_data,
            "relations": relations,
            "channel": channel_data,
            "channel_slug": channel_slug,
            "is_channel_view": True,
            "form_action": AdminURL.entity_form_action("post", entity_id, channel_slug),
            "cancel_url": AdminURL.entity_list("post", channel_slug),
        }
    )

    return templates.TemplateResponse("admin/entity_form.html", context)


@router.post("/channel/{channel_slug}/posts/{entity_id}", response_class=HTMLResponse)
async def channel_post_update(
    request: Request,
    channel_slug: str,
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Update post in channel."""
    entity_svc = EntityService(db)

    # Get channel by slug
    channels = await entity_svc.find("channel", limit=1, filters={"slug": channel_slug})
    if not channels:
        raise HTTPException(status_code=404, detail="Channel not found")
    channel = channels[0]

    # Get entity
    entity = await entity_svc.get(entity_id)
    if not entity or entity.type != "post":
        raise HTTPException(status_code=404, detail="Post not found")

    content_type = field_service.get_content_type("post")
    if not content_type:
        raise HTTPException(status_code=404, detail="Post content type not found")

    # RBAC permission check
    await check_permission(db, current_user, "post", Permission.UPDATE, entity_id)

    form_data = await request.form()
    before_data = entity_svc.serialize(entity)

    # Build entity data from form
    data = parse_form_fields(content_type.fields, form_data)

    try:
        await entity_svc.update(entity_id, data, updated_by=current_user.id)

        # Save relations - ensure channel is linked
        from ..services.relation import RelationService

        relation_svc = RelationService(db)

        for rel in content_type.relations:
            if rel.type == "post_channel":
                await relation_svc.sync(entity_id, [channel.id], rel.type)
            else:
                rel_ids = form_data.getlist(rel.type)
                await relation_svc.sync(entity_id, rel_ids if rel_ids else [], rel.type)

        # Audit log
        if hasattr(request.app.state, "settings") and request.app.state.settings.audit_enabled:
            audit_svc = AuditService(db)
            await audit_svc.log(
                action="update",
                entity_type="post",
                entity_id=entity_id,
                user_id=current_user.id,
                before_data=before_data,
                after_data=data,
                ip_address=get_client_ip(request),
                request_id=get_request_id(request),
            )

        return RedirectResponse(
            url=f"/admin/channel/{channel_slug}/posts?message=Updated+successfully",
            status_code=303,
        )

    except ValueError as e:
        channel_data = entity_svc.serialize(channel)
        relations = await _get_relation_options("post", entity_id, db)
        context = await get_context(request, db, current_user, "post")
        context.update(
            {
                "type_name": "post",
                "content_type": content_type.model_dump(),
                "entity": data,
                "relations": relations,
                "error": str(e),
                "channel": channel_data,
                "channel_slug": channel_slug,
                "is_channel_view": True,
                "form_action": AdminURL.entity_form_action("post", entity_id, channel_slug),
                "cancel_url": AdminURL.entity_list("post", channel_slug),
            }
        )
        return templates.TemplateResponse("admin/entity_form.html", context)


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
    per_page = get_settings().admin.per_page
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
    context.update(
        {
            "type_name": type_name,
            "content_type": content_type.model_dump(),
            "entities": entities,
            "list_fields": [f.model_dump() for f in list_fields],
            "page": page,
            "total_pages": total_pages,
            "message": request.query_params.get("message"),
            "search_query": q,
            "status_filter": status,
        }
    )

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
    context.update(
        {
            "type_name": type_name,
            "content_type": content_type.model_dump(),
            "entity": None,
            "relations": relations,
            "form_action": AdminURL.entity_form_action(type_name),
            "cancel_url": AdminURL.entity_list(type_name),
        }
    )

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

    # RBAC permission check
    await check_permission(db, current_user, type_name, Permission.CREATE)

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
            elif field.type == "password":
                # Password is handled separately for user_auth table
                data["_password_plain"] = value
            elif field.type in ("media", "image"):
                # Handle file upload for media/image type
                if hasattr(value, 'file'):
                    from ..services.media import MediaService
                    media_svc = MediaService(db)
                    media = await media_svc.upload(
                        file=value.file,
                        filename=value.filename,
                        content_type=value.content_type,
                    )
                    data[field.name] = media_svc.serialize(media).get("url")
            else:
                data[field.name] = value

    # Handle password for user type
    password_plain = data.pop("_password_plain", None)

    try:
        user_data = entity_svc.serialize(current_user)
        entity = await entity_svc.create(type_name, data, user_id=user_data.get("id"))
        entity_data = entity_svc.serialize(entity)

        # Create UserAuth record for new user
        if type_name == "user" and password_plain:
            from ..models.auth import UserAuth
            import bcrypt
            salt = bcrypt.gensalt()
            user_auth = UserAuth(
                entity_id=entity.id,
                email=data.get("email", ""),
                password_hash=bcrypt.hashpw(password_plain.encode(), salt).decode(),
            )
            db.add(user_auth)
            await db.commit()

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

        # Auto-assign posts channel for post type if not specified
        if type_name == "post":
            rel_channel_values = form_data.getlist("rel_post_channel")
            channel_ids = [v for v in rel_channel_values if v]
            if not channel_ids:
                from ..services.channel import get_or_create_posts_channel

                posts_channel_id = await get_or_create_posts_channel(db)
                await relation_svc.sync(entity.id, [posts_channel_id], "post_channel")

        # Log create action
        audit_svc = AuditService(db)
        await audit_svc.log_create(
            entity_type=type_name,
            entity_id=entity.id,
            entity_title=entity_data.get("title") or entity_data.get("name") or entity.id,
            data=data,
            user_id=user_data.get("id"),
            user_email=user_data.get("email"),
            user_name=user_data.get("name"),
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            request_id=get_request_id(request),
        )

        return RedirectResponse(
            url=f"/admin/{type_name}?message=Created+successfully",
            status_code=303,
        )

    except ValueError as e:
        relations = await _get_relation_options(type_name, None, db)
        context = await get_context(request, db, current_user, type_name)
        context.update(
            {
                "type_name": type_name,
                "content_type": content_type.model_dump(),
                "entity": data,
                "relations": relations,
                "error": str(e),
                "form_action": AdminURL.entity_form_action(type_name),
                "cancel_url": AdminURL.entity_list(type_name),
            }
        )
        return templates.TemplateResponse("admin/entity_form.html", context)


# === Bulk Actions ===
# NOTE: This must be defined BEFORE /{type_name}/{entity_id} routes
# to prevent "bulk" from being interpreted as an entity_id


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
    context.update(
        {
            "type_name": type_name,
            "content_type": content_type.model_dump(),
            "entity": entity,
            "relations": relations,
            "message": request.query_params.get("message"),
            "form_action": AdminURL.entity_form_action(type_name, entity_id),
            "cancel_url": AdminURL.entity_list(type_name),
        }
    )

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

    # RBAC permission check (includes ownership check for authors)
    await check_permission(db, current_user, type_name, Permission.UPDATE, entity_id)

    form_data = await request.form()

    # DEBUG: フォームデータをログ出力
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[DEBUG] entity_update form_data keys: {list(form_data.keys())}")
    for k, v in form_data.items():
        if 'body' in k.lower() or 'content' in k.lower() or 'block' in k.lower():
            logger.info(f"[DEBUG] form_data[{k}] = {str(v)[:200] if v else 'None'}")

    # Build entity data from form
    import json as json_module

    data = {}
    for field in content_type.fields:
        value = form_data.get(field.name)
        if field.type == 'blocks':
            logger.info(f"[DEBUG] blocks field '{field.name}' value: {str(value)[:200] if value else 'None/Empty'}")
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
            elif field.type == "password":
                # Password is handled separately for user_auth table
                data["_password_plain"] = value
            elif field.type in ("media", "image"):
                # Handle file upload for media/image type
                if hasattr(value, 'file'):
                    from ..services.media import MediaService
                    media_svc = MediaService(db)
                    media = await media_svc.upload(
                        file=value.file,
                        filename=value.filename,
                        content_type=value.content_type,
                    )
                    data[field.name] = media_svc.serialize(media).get("url")
            else:
                data[field.name] = value
        elif field.type == "boolean":
            # Unchecked checkbox
            data[field.name] = False

    # Handle password update for user type
    password_plain = data.pop("_password_plain", None)
    if type_name == "user" and password_plain:
        from ..models.auth import UserAuth
        from sqlalchemy import select
        import bcrypt
        query = select(UserAuth).where(UserAuth.entity_id == entity_id)
        result = await db.execute(query)
        user_auth = result.scalar_one_or_none()
        if user_auth:
            salt = bcrypt.gensalt()
            user_auth.password_hash = bcrypt.hashpw(password_plain.encode(), salt).decode()

    # Save before state for audit
    before_data = entity_svc.serialize(entity_raw)

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

        # Log update action
        entity_after = await entity_svc.get(entity_id)
        after_data = entity_svc.serialize(entity_after) if entity_after else data
        audit_svc = AuditService(db)
        await audit_svc.log_update(
            entity_type=type_name,
            entity_id=entity_id,
            entity_title=after_data.get("title") or after_data.get("name") or entity_id,
            before_data=before_data,
            after_data=after_data,
            user_id=user_data.get("id"),
            user_email=user_data.get("email"),
            user_name=user_data.get("name"),
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            request_id=get_request_id(request),
        )

        return RedirectResponse(
            url=f"/admin/{type_name}/{entity_id}/edit?message=Updated+successfully",
            status_code=303,
        )

    except ValueError as e:
        entity = entity_svc.serialize(entity_raw)
        entity.update(data)  # Show submitted values
        relations = await _get_relation_options(type_name, entity_id, db)

        context = await get_context(request, db, current_user, type_name)
        context.update(
            {
                "type_name": type_name,
                "content_type": content_type.model_dump(),
                "entity": entity,
                "relations": relations,
                "error": str(e),
                "form_action": AdminURL.entity_form_action(type_name, entity_id),
                "cancel_url": AdminURL.entity_list(type_name),
            }
        )
        return templates.TemplateResponse("admin/entity_form.html", context)


# === Entity Delete ===


@router.delete("/{type_name}/{entity_id}")
async def entity_delete(
    request: Request,
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

    # RBAC permission check (includes ownership check for authors)
    await check_permission(db, current_user, type_name, Permission.DELETE, entity_id)

    # Save entity data for audit before deletion
    entity_data = entity_svc.serialize(entity)
    user_data = entity_svc.serialize(current_user)

    # Check if channel is protected from deletion
    if type_name == "channel":
        from ..services.channel import is_protected_channel

        if is_protected_channel(entity_data.get("slug", "")):
            raise HTTPException(
                status_code=400,
                detail="postsチャンネルは削除できません",
            )

    await entity_svc.delete(entity_id, user_id=user_data.get("id"))

    # Log delete action
    audit_svc = AuditService(db)
    await audit_svc.log_delete(
        entity_type=type_name,
        entity_id=entity_id,
        entity_title=entity_data.get("title") or entity_data.get("name") or entity_id,
        data=entity_data,
        user_id=user_data.get("id"),
        user_email=user_data.get("email"),
        user_name=user_data.get("name"),
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        request_id=get_request_id(request),
    )

    # Return empty response for HTMX to remove the row
    return HTMLResponse(content="", status_code=200)


@router.post("/{type_name}/{entity_id}/delete")
async def entity_delete_post(
    request: Request,
    type_name: str,
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Entity = Depends(require_admin),
):
    """Delete entity via POST (for HTML forms)."""
    # Perform the delete
    entity_svc = EntityService(db)
    entity = await entity_svc.get(entity_id)
    if not entity or entity.type != type_name:
        raise HTTPException(status_code=404, detail="Entity not found")

    # RBAC permission check
    await check_permission(db, current_user, type_name, Permission.DELETE, entity_id)

    # Save entity data for audit before deletion
    entity_data = entity_svc.serialize(entity)
    user_data = entity_svc.serialize(current_user)

    # Check if channel is protected from deletion
    if type_name == "channel":
        from ..services.channel import is_protected_channel

        if is_protected_channel(entity_data.get("slug", "")):
            raise HTTPException(
                status_code=400,
                detail="postsチャンネルは削除できません",
            )

    await entity_svc.delete(entity_id, user_id=user_data.get("id"))

    # Log delete action
    audit_svc = AuditService(db)
    await audit_svc.log_delete(
        entity_type=type_name,
        entity_id=entity_id,
        entity_title=entity_data.get("title") or entity_data.get("name") or entity_id,
        data=entity_data,
        user_id=user_data.get("id"),
        user_email=user_data.get("email"),
        user_name=user_data.get("name"),
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        request_id=get_request_id(request),
    )

    # Redirect to list page for regular form submissions
    return RedirectResponse(
        url=f"/admin/{type_name}?message=Deleted+successfully",
        status_code=303,
    )


# === Helper Functions ===


async def _get_relation_options(
    type_name: str,
    entity_id: str | None,
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
            options.append(
                {
                    "id": target.id,
                    "label": label,
                    "selected": target.id in current_ids,
                }
            )

        relations.append(
            {
                "name": rel.type,
                "label": rel_def.label if rel_def.label else rel.type,
                "multiple": rel_def.type in ("many_to_many", "one_to_many"),
                "options": options,
            }
        )

    return relations
