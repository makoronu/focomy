"""Focomy - The Most Beautiful CMS."""

import secrets
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from . import __version__
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response

from .config import settings
from .database import close_db, init_db
from .rate_limit import limiter
from .services.logging import bind_context, clear_context, configure_logging, get_logger


class RedirectMiddleware(BaseHTTPMiddleware):
    """Handle URL redirects before other processing."""

    # Skip paths that should not be redirected
    SKIP_PREFIXES = ("/api/", "/admin/", "/static/", "/uploads/", "/health")

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip certain paths
        if any(path.startswith(prefix) for prefix in self.SKIP_PREFIXES):
            return await call_next(request)

        # Only check redirects for GET requests
        if request.method != "GET":
            return await call_next(request)

        try:
            from .database import async_session
            from .services.redirect import RedirectService

            async with async_session() as db:
                redirect_svc = RedirectService(db)
                query_string = str(request.url.query) if request.url.query else ""
                redirect = await redirect_svc.find_redirect(path, query_string)

                if redirect:
                    from starlette.responses import RedirectResponse

                    return RedirectResponse(
                        url=redirect["to_path"],
                        status_code=redirect["status_code"],
                    )
        except Exception:
            # Don't break the site if redirect service fails
            pass

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add comprehensive security headers to all responses."""

    # CSP for admin pages (allow inline styles/scripts for Editor.js)
    ADMIN_CSP = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data: https: blob:; "
        "font-src 'self' https://fonts.gstatic.com; "
        "frame-src https://www.youtube.com https://player.vimeo.com https://open.spotify.com "
        "https://w.soundcloud.com https://www.google.com https://maps.google.com; "
        "connect-src 'self' https://www.googletagmanager.com"
    )

    # CSP for public pages (more restrictive)
    PUBLIC_CSP = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://www.googletagmanager.com https://www.google-analytics.com https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data: https: blob:; "
        "font-src 'self' https://fonts.gstatic.com; "
        "frame-src https://www.youtube.com https://player.vimeo.com https://open.spotify.com "
        "https://w.soundcloud.com https://www.google.com https://maps.google.com; "
        "connect-src 'self' https://www.google-analytics.com; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "upgrade-insecure-requests"
    )

    # Permissions Policy (formerly Feature-Policy)
    PERMISSIONS_POLICY = (
        "accelerometer=(), "
        "ambient-light-sensor=(), "
        "autoplay=(self), "
        "battery=(), "
        "camera=(), "
        "display-capture=(), "
        "document-domain=(), "
        "encrypted-media=(self), "
        "fullscreen=(self), "
        "geolocation=(), "
        "gyroscope=(), "
        "magnetometer=(), "
        "microphone=(), "
        "midi=(), "
        "payment=(), "
        "picture-in-picture=(self), "
        "publickey-credentials-get=(), "
        "screen-wake-lock=(), "
        "usb=(), "
        "xr-spatial-tracking=()"
    )

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        headers_config = settings.security.headers

        # Basic security headers (always applied)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # X-Frame-Options
        if headers_config.frame_options:
            response.headers["X-Frame-Options"] = headers_config.frame_options

        # HSTS (only for HTTPS in production)
        if headers_config.hsts_enabled and not settings.debug:
            hsts_value = f"max-age={headers_config.hsts_max_age}"
            if headers_config.hsts_include_subdomains:
                hsts_value += "; includeSubDomains"
            if headers_config.hsts_preload:
                hsts_value += "; preload"
            response.headers["Strict-Transport-Security"] = hsts_value

        # Content Security Policy
        if headers_config.csp_enabled:
            csp_header = "Content-Security-Policy"
            if headers_config.csp_report_only:
                csp_header = "Content-Security-Policy-Report-Only"

            if request.url.path.startswith("/admin"):
                response.headers[csp_header] = self.ADMIN_CSP
            elif not request.url.path.startswith("/api"):
                response.headers[csp_header] = self.PUBLIC_CSP

        # Cache-Control for admin pages (prevent stale content)
        if request.url.path.startswith("/admin"):
            response.headers["Cache-Control"] = "no-store, must-revalidate"

        # Permissions Policy
        if headers_config.permissions_policy_enabled:
            response.headers["Permissions-Policy"] = self.PERMISSIONS_POLICY

        # Cross-Origin headers for additional isolation
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"

        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """CSRF protection middleware.

    This middleware:
    1. Generates/retrieves CSRF tokens and stores in cookies
    2. Makes token available in request.state for templates
    3. Validates X-CSRF-Token header for AJAX requests

    For form submissions, routes should validate CSRF using the
    validate_csrf_token() helper function.
    """

    SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
    CSRF_COOKIE_NAME = "csrf_token"
    CSRF_HEADER_NAME = "x-csrf-token"

    async def dispatch(self, request: Request, call_next):
        # Skip CSRF for API routes (use bearer tokens or session auth)
        if request.url.path.startswith("/api/") or request.url.path.startswith("/admin/api/"):
            return await call_next(request)

        # Get or create CSRF token
        csrf_token = request.cookies.get(self.CSRF_COOKIE_NAME)
        if not csrf_token:
            csrf_token = secrets.token_urlsafe(32)

        # Store token in request state for templates
        request.state.csrf_token = csrf_token

        # Validate CSRF header for unsafe methods (AJAX requests)
        if request.method not in self.SAFE_METHODS:
            header_token = request.headers.get(self.CSRF_HEADER_NAME)
            content_type = request.headers.get("content-type", "")

            # For AJAX requests with JSON, require header
            if "application/json" in content_type:
                if header_token != csrf_token:
                    raise HTTPException(status_code=403, detail="CSRF token required")
            # For form submissions, let the route handler validate via form field
            # (This avoids body consumption issues in middleware)

        response = await call_next(request)

        # Set CSRF cookie
        response.set_cookie(
            key=self.CSRF_COOKIE_NAME,
            value=csrf_token,
            httponly=False,  # Needs to be readable by JS for AJAX
            samesite="lax",
            secure=not settings.debug,
        )

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Structured request/response logging middleware.

    Logs every request with timing, status, and context.
    Assigns a unique request ID for tracing.
    """

    # Skip logging for these paths to reduce noise
    SKIP_PATHS = {"/health", "/favicon.ico"}

    async def dispatch(self, request: Request, call_next):
        # Skip health checks and favicon
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        # Generate request ID
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        # Bind context for all logs in this request
        bind_context(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        # Get client IP (handle proxies)
        client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.client.host if request.client else "unknown"

        logger = get_logger("focomy.http")
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log based on status code
            log_data = {
                "client_ip": client_ip,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "user_agent": request.headers.get("user-agent", "")[:100],
            }

            if response.status_code >= 500:
                logger.error("Request failed", **log_data)
            elif response.status_code >= 400:
                logger.warning("Request error", **log_data)
            else:
                logger.info("Request completed", **log_data)

            # Add request ID to response headers for debugging
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "Request exception",
                client_ip=client_ip,
                duration_ms=round(duration_ms, 2),
                error=str(e),
            )
            raise
        finally:
            clear_context()


def validate_csrf_token(request: Request, form_token: str) -> bool:
    """Validate CSRF token from form data against cookie.

    Call this in form-handling routes:
        if not validate_csrf_token(request, form.csrf_token):
            raise HTTPException(403, "CSRF token mismatch")
    """
    cookie_token = request.cookies.get("csrf_token")
    return cookie_token and form_token == cookie_token


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Configure structured logging first
    configure_logging()
    logger = get_logger("focomy")
    logger.info("Starting Focomy CMS", version=__version__, debug=settings.debug)

    # Startup
    await init_db()
    logger.info("Database initialized")

    # Security warnings
    if settings.security.secret_key == "change-this-in-production":
        logger.warning(
            "SECURITY: secret_key is using default value. "
            "Set FOCOMY_SECURITY__SECRET_KEY environment variable in production."
        )
    if "*" in settings.cors.allow_origins:
        logger.warning(
            "SECURITY: CORS allows all origins (*). "
            "Set FOCOMY_CORS__ALLOW_ORIGINS to specific domains in production."
        )

    # Configure OAuth
    from .services.oauth import oauth_service

    oauth_service.configure(app)
    logger.info("OAuth configured")

    yield

    # Shutdown
    logger.info("Shutting down Focomy CMS")
    await close_db()


app = FastAPI(
    title="Focomy",
    description="The Most Beautiful CMS",
    version=__version__,
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Security middlewares (order matters - first added = last executed)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(SessionMiddleware, secret_key=settings.security.secret_key)
app.add_middleware(RedirectMiddleware)

# Request logging (runs early, logs all requests)
app.add_middleware(RequestLoggingMiddleware)

# CORS middleware (configurable via settings)
if settings.cors.enabled:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors.allow_origins,
        allow_credentials=settings.cors.allow_credentials,
        allow_methods=settings.cors.allow_methods,
        allow_headers=settings.cors.allow_headers,
        max_age=settings.cors.max_age,
    )

# Static files - ディレクトリが存在する場合のみマウント
uploads_dir = settings.base_dir / "uploads"
uploads_dir.mkdir(exist_ok=True)
app.mount(
    "/uploads",
    StaticFiles(directory=str(uploads_dir)),
    name="uploads",
)

# Static assets (favicon, css, js)
static_dir = settings.base_dir / "static"
static_dir.mkdir(exist_ok=True)
app.mount(
    "/static",
    StaticFiles(directory=str(static_dir)),
    name="static",
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


# Exception handlers
from fastapi.responses import HTMLResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: StarletteHTTPException):
    """Handle 404 errors."""
    # Return JSON for API routes
    if request.url.path.startswith("/api/"):
        return Response(
            content='{"detail": "Not found"}', status_code=404, media_type="application/json"
        )

    # Render HTML error page for frontend
    from .services.theme import theme_service

    try:
        html = theme_service.render(
            "404.html",
            {"site_name": "Focomy"},
        )
        return HTMLResponse(content=html, status_code=404)
    except Exception:
        return HTMLResponse(content="<h1>404 - Not Found</h1>", status_code=404)


@app.exception_handler(500)
async def server_error_handler(request: Request, exc: Exception):
    """Handle 500 errors."""
    # Return JSON for API routes
    if request.url.path.startswith("/api/"):
        return Response(
            content='{"detail": "Internal server error"}',
            status_code=500,
            media_type="application/json",
        )

    # Render HTML error page for frontend
    from .services.theme import theme_service

    try:
        html = theme_service.render(
            "500.html",
            {"site_name": "Focomy"},
        )
        return HTMLResponse(content=html, status_code=500)
    except Exception:
        return HTMLResponse(content="<h1>500 - Internal Server Error</h1>", status_code=500)


# Include routers
from .admin import routes as admin
from .api import auth, comments, entities, forms, media, relations, revisions, schema, search, seo
from .engine import routes as engine

# Phase 1: Core APIs (always enabled)
app.include_router(entities.router, prefix="/api")
app.include_router(schema.router, prefix="/api")
app.include_router(relations.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(seo.router)
app.include_router(admin.router)

# Phase 2: Media (runtime check in endpoints)
app.include_router(media.router, prefix="/api")

# Phase 4: Search, Revisions (runtime check in endpoints)
app.include_router(search.router, prefix="/api")
app.include_router(revisions.router, prefix="/api")

# Phase 5: Comments, Forms (runtime check in endpoints)
app.include_router(comments.router, prefix="/api")
app.include_router(forms.router)


@app.get("/api/health")
async def api_health():
    """Health check endpoint for monitoring."""
    return {"status": "healthy"}


# Engine router must be last (has catch-all routes)
app.include_router(engine.router)
