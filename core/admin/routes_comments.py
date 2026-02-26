"""Admin comment routes - moderation."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import get_db
from ..models import Entity
from ..services.entity import EntityService
from .helpers import templates, require_admin, get_context

router = APIRouter()


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
