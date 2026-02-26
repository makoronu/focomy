"""Admin routes - thin coordinator that assembles all sub-routers."""

from fastapi import APIRouter

from .routes_auth import router as auth_router
from .routes_comments import router as comments_router
from .routes_dashboard import router as dashboard_router
from .routes_entity import router as entity_router
from .routes_entity_edit import router as entity_edit_router
from .routes_import import router as import_router
from .routes_import_exec import router as import_exec_router
from .routes_import_ops import router as import_ops_router
from .routes_import_preview import router as import_preview_router
from .routes_menus import router as menus_router
from .routes_posts import router as posts_router
from .routes_redirects import router as redirects_router
from .routes_settings import router as settings_router
from .routes_system import router as system_router
from .routes_themes import router as themes_router
from .routes_tools import router as tools_router
from .routes_widgets import router as widgets_router

router = APIRouter(prefix="/admin", tags=["admin"])

# === Fixed-path routes (must come before dynamic /{type_name} routes) ===
router.include_router(auth_router)
router.include_router(dashboard_router)
router.include_router(widgets_router)
router.include_router(themes_router)
router.include_router(settings_router)
router.include_router(menus_router)
router.include_router(tools_router)
router.include_router(redirects_router)
router.include_router(comments_router)
router.include_router(system_router)

# === Import routes ===
router.include_router(import_router)
router.include_router(import_preview_router)
router.include_router(import_ops_router)
router.include_router(import_exec_router)

# === Channel/orphan posts ===
router.include_router(posts_router)

# === Dynamic entity routes (MUST be last - /{type_name} catches all) ===
router.include_router(entity_router)
router.include_router(entity_edit_router)
