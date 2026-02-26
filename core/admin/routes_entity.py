"""Admin routes - Entity list, create, and bulk actions."""

import json as json_module

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
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

router = APIRouter()


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
    relations = await get_relation_options(type_name, None, db)

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
        relations = await get_relation_options(type_name, None, db)
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
