"""Admin post routes - channel posts, orphan posts."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import get_db
from ..models import Entity
from ..services.audit import AuditService, get_client_ip, get_request_id
from ..services.entity import EntityService
from ..services.field import field_service
from ..services.rbac import Permission
from .helpers import templates, require_admin, get_context, parse_form_fields, check_permission
from .url import AdminURL

router = APIRouter()


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
    from .helpers import get_relation_options

    relations = await get_relation_options("post", None, db)

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
        from .helpers import get_relation_options

        channel_data = entity_svc.serialize(channel)
        relations = await get_relation_options("post", None, db)
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

    from .helpers import get_relation_options

    relations = await get_relation_options("post", entity_id, db)

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
        from .helpers import get_relation_options

        channel_data = entity_svc.serialize(channel)
        relations = await get_relation_options("post", entity_id, db)
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
