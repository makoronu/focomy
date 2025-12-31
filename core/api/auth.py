"""Auth API endpoints - authentication.

This module provides authentication endpoints for user registration,
login/logout, password management, and OAuth integration.

Security features:
- Rate limiting on login/register (5 per minute)
- Session-based authentication with secure cookies
- Password hashing with bcrypt
- OAuth support (Google, etc.)
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..rate_limit import limiter
from ..services.auth import AuthService
from ..services.entity import EntityService

router = APIRouter(prefix="/auth", tags=["Authentication"])


class RegisterRequest(BaseModel):
    """Request body for user registration."""

    email: EmailStr = Field(..., description="User email address", examples=["user@example.com"])
    password: str = Field(..., min_length=12, description="Password (min 12 characters)")
    name: str = Field(..., description="Display name", examples=["John Doe"])
    role: str = Field("author", description="User role (admin, editor, author)")


class LoginRequest(BaseModel):
    """Request body for user login."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class ChangePasswordRequest(BaseModel):
    """Request body for password change."""

    old_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=12, description="New password (min 12 characters)")


def get_session_token(request: Request) -> str | None:
    """Extract session token from cookie or header."""
    # Try cookie first
    token = request.cookies.get("session")
    if token:
        return token

    # Try Authorization header
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth[7:]

    return None


@router.post(
    "/register",
    summary="Register new user",
    description="Create a new user account. Rate limited to 5 requests per minute.",
    responses={
        200: {
            "description": "User created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "user123",
                        "email": "user@example.com",
                        "name": "John Doe",
                        "role": "author",
                    }
                }
            },
        },
        400: {"description": "Email already exists or validation error"},
    },
)
@limiter.limit("5/minute")
async def register(
    request: Request,
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Register a new user.

    Creates a new user account with the specified credentials.
    Password must be at least 12 characters.
    """
    auth_svc = AuthService(db)

    try:
        user = await auth_svc.register(
            email=body.email,
            password=body.password,
            name=body.name,
            role=body.role,
        )
        entity_svc = EntityService(db)
        data = entity_svc.serialize(user)
        data.pop("password", None)  # Security: never return password hash
        return data
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/login",
    summary="User login",
    description="Authenticate with email and password. Rate limited to 5 requests per minute.",
    responses={
        200: {
            "description": "Login successful",
            "content": {
                "application/json": {
                    "example": {
                        "user": {"id": "user123", "email": "user@example.com", "name": "John"},
                        "token": "eyJhbGciOiJIUzI1NiIs...",
                    }
                }
            },
        },
        401: {"description": "Invalid credentials or account locked"},
    },
)
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Login with email and password.

    On success, sets a session cookie and returns user data with a JWT token.
    The token can be used in the Authorization header for API requests.
    """
    auth_svc = AuthService(db)

    try:
        user, token = await auth_svc.login(
            email=body.email,
            password=body.password,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
        )

        # Set session cookie
        response.set_cookie(
            key="session",
            value=token,
            httponly=True,
            secure=False,  # Set True in production with HTTPS
            samesite="lax",
            max_age=86400,  # 24 hours
        )

        entity_svc = EntityService(db)
        return {
            "user": entity_svc.serialize(user),
            "token": token,
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post(
    "/logout",
    summary="User logout",
    description="Invalidate the current session and clear cookies.",
    responses={
        200: {
            "description": "Logged out successfully",
            "content": {"application/json": {"example": {"status": "logged_out"}}},
        }
    },
)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Logout and destroy session.

    Clears the session cookie and invalidates the server-side session.
    """
    token = get_session_token(request)
    if token:
        auth_svc = AuthService(db)
        await auth_svc.logout(token)

    response.delete_cookie("session")
    return {"status": "logged_out"}


@router.get(
    "/me",
    summary="Get current user",
    description="Retrieve the currently authenticated user's profile.",
    responses={
        200: {
            "description": "Current user profile",
            "content": {
                "application/json": {
                    "example": {
                        "id": "user123",
                        "email": "user@example.com",
                        "name": "John Doe",
                        "role": "admin",
                    }
                }
            },
        },
        401: {"description": "Not authenticated or session expired"},
    },
)
async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get current authenticated user.

    Requires a valid session cookie or Authorization header.
    """
    token = get_session_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    auth_svc = AuthService(db)
    user = await auth_svc.get_current_user(token)

    if not user:
        raise HTTPException(status_code=401, detail="Session expired")

    entity_svc = EntityService(db)
    return entity_svc.serialize(user)


@router.post(
    "/change-password",
    summary="Change password",
    description="Change password for the currently authenticated user.",
    responses={
        200: {
            "description": "Password changed successfully",
            "content": {"application/json": {"example": {"status": "password_changed"}}},
        },
        400: {"description": "Invalid old password or new password too weak"},
        401: {"description": "Not authenticated"},
    },
)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Change password for current user.

    Requires the current password and a new password (min 12 characters).
    """
    token = get_session_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    auth_svc = AuthService(db)
    user = await auth_svc.get_current_user(token)

    if not user:
        raise HTTPException(status_code=401, detail="Session expired")

    try:
        await auth_svc.change_password(
            user_id=user.id,
            old_password=body.old_password,
            new_password=body.new_password,
        )
        return {"status": "password_changed"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# === OAuth ===


@router.get(
    "/oauth/{provider}",
    summary="Initiate OAuth login",
    description="Start OAuth authentication flow with the specified provider.",
    responses={
        307: {"description": "Redirect to OAuth provider"},
        400: {"description": "Provider not configured"},
    },
)
async def oauth_login(
    provider: str,
    request: Request,
):
    """Initiate OAuth login flow.

    Redirects to the OAuth provider's authorization page.
    Supported providers: google
    """
    from ..services.oauth import oauth_service

    if not oauth_service.is_configured(provider):
        raise HTTPException(status_code=400, detail=f"Provider {provider} not configured")

    # Build redirect URI
    redirect_uri = str(request.base_url).rstrip("/") + f"/api/auth/oauth/{provider}/callback"

    return await oauth_service.get_authorization_url(provider, redirect_uri, request)


@router.get(
    "/oauth/{provider}/callback",
    summary="OAuth callback",
    description="Handle callback from OAuth provider after user authorization.",
    responses={
        303: {"description": "Redirect to admin dashboard on success"},
        400: {"description": "OAuth authentication failed"},
    },
)
async def oauth_callback(
    provider: str,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Handle OAuth callback.

    Processes the OAuth authorization code, creates/updates user,
    and redirects to admin dashboard.
    """
    from ..services.oauth import oauth_service

    user_info = await oauth_service.handle_callback(provider, request)

    if not user_info:
        raise HTTPException(status_code=400, detail="OAuth authentication failed")

    auth_svc = AuthService(db)
    entity_svc = EntityService(db)

    # Find or create user by email
    users = await entity_svc.find(
        "user",
        limit=1,
        filters={"email": user_info.email},
    )

    if users:
        user = users[0]
    else:
        # Create new user
        user = await auth_svc.register(
            email=user_info.email,
            password=None,  # No password for OAuth users
            name=user_info.name,
            role="author",
        )
        # Update with provider info
        await entity_svc.update(
            user.id,
            {
                "oauth_provider": user_info.provider,
                "oauth_id": user_info.provider_id,
                "avatar": user_info.picture,
            },
        )

    # Create session
    user, token = await auth_svc.login_oauth(user)

    # Set cookie and redirect
    from fastapi.responses import RedirectResponse

    redirect_response = RedirectResponse(url="/admin", status_code=303)
    redirect_response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=False,  # Set True in production
        samesite="lax",
        max_age=86400,
    )

    return redirect_response
