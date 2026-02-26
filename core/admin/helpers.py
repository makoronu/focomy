"""Admin helpers - shared utilities for admin routes."""

from pathlib import Path
from typing import Any

import json as json_module

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import get_db
from ..models import Entity
from ..services.auth import AuthService
from ..services.entity import EntityService
from ..services.field import field_service
from ..services.rbac import Permission, RBACService
from ..services.relation import RelationService
from .url import AdminURL

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


async def get_relation_options(
    type_name: str,
    entity_id: str | None,
    db: AsyncSession,
) -> list:
    """Get relation options for entity form."""
    content_type = field_service.get_content_type(type_name)
    if not content_type or not content_type.relations:
        return []

    entity_svc = EntityService(db)
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
