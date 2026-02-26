"""Admin auth routes - login, logout, password reset."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..rate_limit import limiter
from ..services.audit import AuditService, get_client_ip, get_request_id
from ..services.auth import AuthService
from ..services.entity import EntityService
from .helpers import templates, require_admin, get_context, get_current_admin

router = APIRouter()


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
