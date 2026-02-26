"""Admin routes - Entity edit, update, and delete operations."""

import json as json_module
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Entity
from ..services.audit import AuditService, get_client_ip, get_request_id
from ..services.entity import EntityService
from ..services.field import field_service
from ..services.rbac import Permission
from .helpers import (
    check_permission,
    get_context,
    get_relation_options,
    require_admin,
    templates,
)
from .url import AdminURL

logger = logging.getLogger(__name__)

router = APIRouter()


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
    relations = await get_relation_options(type_name, entity_id, db)

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
    logger.info(f"[DEBUG] entity_update form_data keys: {list(form_data.keys())}")
    for k, v in form_data.items():
        if 'body' in k.lower() or 'content' in k.lower() or 'block' in k.lower():
            logger.info(f"[DEBUG] form_data[{k}] = {str(v)[:200] if v else 'None'}")

    # Build entity data from form
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
        relations = await get_relation_options(type_name, entity_id, db)

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
