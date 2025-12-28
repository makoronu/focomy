"""Comment API endpoints - public comment submission and retrieval."""

from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..rate_limit import limiter
from ..services.comment import CommentService

router = APIRouter(prefix="/comments", tags=["Comments"])


class CommentCreate(BaseModel):
    """Request body for creating a comment."""

    post_id: str = Field(..., description="ID of the post to comment on")
    author_name: str = Field(..., min_length=1, max_length=100, description="Author display name")
    author_email: EmailStr = Field(..., description="Author email address")
    content: str = Field(..., min_length=1, max_length=2000, description="Comment content")
    parent_id: str | None = Field(None, description="Parent comment ID for replies")
    honeypot: str | None = Field(None, description="Honeypot field (should be empty)")


class CommentResponse(BaseModel):
    """Response for a single comment."""

    id: str
    author_name: str
    content: str
    status: str
    created_at: str
    children: list[dict[str, Any]] = []


@router.post(
    "",
    summary="Submit a comment",
    description="Submit a new comment on a post. Comments require moderation before being published.",
    responses={
        200: {
            "description": "Comment submitted successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "pending",
                        "message": "Your comment has been submitted for review.",
                    }
                }
            },
        },
        400: {"description": "Invalid input or spam detected"},
        429: {"description": "Rate limit exceeded"},
    },
)
@limiter.limit("5/minute")
async def create_comment(
    request: Request,
    body: CommentCreate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Create a new comment.

    Comments are submitted with status 'pending' and require admin approval.
    Honeypot and rate limiting are used for spam protection.
    """
    comment_svc = CommentService(db)

    # Get IP and user agent
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent", "")

    result = await comment_svc.create_comment(
        post_id=body.post_id,
        author_name=body.author_name,
        author_email=body.author_email,
        content=body.content,
        ip_address=ip_address,
        user_agent=user_agent,
        parent_id=body.parent_id,
        honeypot=body.honeypot,
    )

    if not result:
        raise HTTPException(
            status_code=400, detail="Comment could not be submitted. Please try again later."
        )

    return {
        "status": "pending",
        "message": "Your comment has been submitted for review.",
        "id": result.get("id", ""),
    }


@router.post(
    "/form",
    response_class=HTMLResponse,
    summary="Submit comment via form (HTMX)",
    description="Submit a comment via HTML form. Returns HTML response for HTMX.",
)
@limiter.limit("5/minute")
async def create_comment_form(
    request: Request,
    post_id: str = Form(...),
    author_name: str = Form(...),
    author_email: str = Form(...),
    content: str = Form(...),
    parent_id: str = Form(""),
    website: str = Form(""),  # Honeypot field
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Create a comment via HTML form submission.

    Returns HTML response for HTMX integration.
    The 'website' field is a honeypot - if filled, the comment is rejected.
    """
    comment_svc = CommentService(db)

    # Get IP and user agent
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent", "")

    result = await comment_svc.create_comment(
        post_id=post_id,
        author_name=author_name.strip(),
        author_email=author_email.strip(),
        content=content.strip(),
        ip_address=ip_address,
        user_agent=user_agent,
        parent_id=parent_id if parent_id else None,
        honeypot=website,  # Honeypot field
    )

    if not result:
        return HTMLResponse(
            content="""
            <div class="comment-response comment-error">
                <p>コメントを送信できませんでした。しばらく経ってから再度お試しください。</p>
            </div>
            """,
            status_code=200,  # Return 200 for HTMX to process
        )

    return HTMLResponse(
        content="""
        <div class="comment-response comment-success">
            <p>コメントを送信しました。承認後に表示されます。</p>
        </div>
        """,
        status_code=200,
    )


@router.get(
    "/{post_id}",
    summary="Get comments for a post",
    description="Retrieve approved comments for a specific post.",
    responses={
        200: {
            "description": "List of approved comments",
            "content": {
                "application/json": {
                    "example": {
                        "comments": [
                            {
                                "id": "abc123",
                                "author_name": "John",
                                "content": "Great post!",
                                "created_at": "2024-01-15T10:30:00Z",
                                "children": [],
                            }
                        ]
                    }
                }
            },
        }
    },
)
async def get_comments(
    post_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, list]:
    """Get approved comments for a post.

    Returns a nested tree structure of comments.
    Only approved comments are included.
    """
    comment_svc = CommentService(db)
    comments = await comment_svc.get_comments_for_post(post_id)

    return {"comments": [c.to_dict() for c in comments]}


@router.get(
    "/{post_id}/html",
    response_class=HTMLResponse,
    summary="Get comments as HTML (HTMX)",
    description="Retrieve approved comments as rendered HTML for HTMX.",
)
async def get_comments_html(
    post_id: str,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Get comments for a post as HTML.

    Returns rendered HTML for HTMX integration.
    """
    comment_svc = CommentService(db)
    comments = await comment_svc.get_comments_for_post(post_id)

    if not comments:
        return HTMLResponse(
            content='<p class="no-comments">まだコメントはありません。</p>',
            status_code=200,
        )

    html = _render_comments_html(comments)
    return HTMLResponse(content=html, status_code=200)


def _render_comments_html(comments: list, level: int = 0) -> str:
    """Render comments as HTML recursively."""
    html_parts = []

    for comment in comments:
        indent_class = f"comment-level-{min(level, 3)}"
        html_parts.append(
            f"""
        <div class="comment {indent_class}" id="comment-{comment.id}">
            <div class="comment-header">
                <span class="comment-author">{_escape_html(comment.author_name)}</span>
                <span class="comment-date">{comment.created_at[:10]}</span>
            </div>
            <div class="comment-content">
                {_escape_html(comment.content).replace(chr(10), '<br>')}
            </div>
            <div class="comment-actions">
                <button type="button" class="reply-btn" data-parent-id="{comment.id}">
                    返信
                </button>
            </div>
        """
        )

        if comment.children:
            html_parts.append('<div class="comment-replies">')
            html_parts.append(_render_comments_html(comment.children, level + 1))
            html_parts.append("</div>")

        html_parts.append("</div>")

    return "".join(html_parts)


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
