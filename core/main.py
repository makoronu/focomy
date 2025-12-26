"""Focomy - The Most Beautiful CMS."""

from contextlib import asynccontextmanager
import secrets

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .config import settings
from .database import init_db, close_db
from .rate_limit import limiter


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # CSP for admin pages (allow inline styles/scripts for Editor.js)
        if request.url.path.startswith("/admin"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "frame-src https://www.youtube.com https://player.vimeo.com https://open.spotify.com https://w.soundcloud.com https://www.google.com https://maps.google.com; "
                "connect-src 'self'"
            )
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
        # Skip CSRF for API routes (use bearer tokens)
        if request.url.path.startswith("/api/"):
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
    # Startup
    await init_db()

    # Configure OAuth
    from .services.oauth import oauth_service
    oauth_service.configure(app)

    yield
    # Shutdown
    await close_db()


app = FastAPI(
    title="Focomy",
    description="The Most Beautiful CMS",
    version="0.1.0",
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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount(
    "/uploads",
    StaticFiles(directory=str(settings.base_dir / "uploads")),
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
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import HTMLResponse

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: StarletteHTTPException):
    """Handle 404 errors."""
    # Return JSON for API routes
    if request.url.path.startswith("/api/"):
        return Response(
            content='{"detail": "Not found"}',
            status_code=404,
            media_type="application/json"
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
        return HTMLResponse(
            content="<h1>404 - Not Found</h1>",
            status_code=404
        )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc: Exception):
    """Handle 500 errors."""
    # Return JSON for API routes
    if request.url.path.startswith("/api/"):
        return Response(
            content='{"detail": "Internal server error"}',
            status_code=500,
            media_type="application/json"
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
        return HTMLResponse(
            content="<h1>500 - Internal Server Error</h1>",
            status_code=500
        )


# Include routers
from .api import entities, schema, relations, auth, media, seo, forms, revisions, comments
from .admin import routes as admin
from .engine import routes as engine

app.include_router(entities.router, prefix="/api")
app.include_router(schema.router, prefix="/api")
app.include_router(relations.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(media.router, prefix="/api")
app.include_router(revisions.router, prefix="/api")
app.include_router(comments.router, prefix="/api")
app.include_router(forms.router)
app.include_router(seo.router)
app.include_router(admin.router)
app.include_router(engine.router)
