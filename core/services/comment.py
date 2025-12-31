"""CommentService - comment management with moderation.

Features:
- Nested/threaded comments
- Moderation (approve, reject, spam)
- Honeypot spam protection
- Rate limiting
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .entity import EntityService
from .relation import RelationService


@dataclass
class CommentData:
    """Structured comment data for templates."""

    id: str
    author_name: str
    author_email: str
    content: str
    status: str
    created_at: str
    children: list["CommentData"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for templates."""
        return {
            "id": self.id,
            "author_name": self.author_name,
            "author_email": self.author_email,
            "content": self.content,
            "status": self.status,
            "created_at": self.created_at,
            "children": [c.to_dict() for c in self.children],
        }


class CommentService:
    """
    Comment management service.

    Handles comment CRUD, moderation, and spam protection.
    """

    # Rate limit: max comments per IP per minute
    RATE_LIMIT = 5
    RATE_WINDOW = 60  # seconds

    def __init__(self, db: AsyncSession):
        self.db = db
        self.entity_svc = EntityService(db)
        self.relation_svc = RelationService(db)

    async def create_comment(
        self,
        post_id: str,
        author_name: str,
        author_email: str,
        content: str,
        ip_address: str = None,
        user_agent: str = None,
        parent_id: str = None,
        honeypot: str = None,
    ) -> dict[str, Any] | None:
        """
        Create a new comment.

        Returns None if spam detected or rate limited.
        """
        # Honeypot check - if filled, it's spam
        if honeypot:
            return None

        # Rate limit check
        if ip_address and not await self._check_rate_limit(ip_address):
            return None

        # Basic content validation
        content = content.strip()
        if not content or len(content) > 2000:
            return None

        # Create comment entity
        data = {
            "author_name": author_name.strip()[:100],
            "author_email": author_email.strip()[:255],
            "content": content,
            "status": "pending",  # Requires moderation
            "ip_address": ip_address[:45] if ip_address else "",
            "user_agent": user_agent[:500] if user_agent else "",
        }

        entity = await self.entity_svc.create("comment", data)

        # Set post relation
        await self.relation_svc.attach(entity.id, post_id, "comment_post")

        # Set parent relation if replying
        if parent_id:
            await self.relation_svc.attach(entity.id, parent_id, "comment_parent")

        return self.entity_svc.serialize(entity)

    async def get_comments_for_post(
        self,
        post_id: str,
        include_pending: bool = False,
    ) -> list[CommentData]:
        """
        Get approved comments for a post, organized as a tree.

        Returns nested comment structure.
        """
        # Get all comments related to this post
        related = await self.relation_svc.get_related(post_id, "comment_post", direction="to")

        if not related:
            return []

        # Filter by status and build data
        comments = []
        for e in related:
            data = self.entity_svc.serialize(e)
            status = data.get("status", "pending")

            if status == "approved" or (include_pending and status == "pending"):
                # Get parent relation
                parent_relations = await self.relation_svc.get_relations(
                    e.id, "comment_parent", direction="from"
                )
                parent_id = parent_relations[0].to_entity_id if parent_relations else None

                comments.append(
                    {
                        "id": e.id,
                        "author_name": data.get("author_name", ""),
                        "author_email": data.get("author_email", ""),
                        "content": data.get("content", ""),
                        "status": status,
                        "created_at": data.get("created_at", ""),
                        "parent_id": parent_id,
                    }
                )

        # Build tree
        return self._build_comment_tree(comments)

    def _build_comment_tree(self, comments: list[dict]) -> list[CommentData]:
        """Build nested comment tree from flat list."""
        # Sort by created_at
        comments = sorted(comments, key=lambda c: c.get("created_at", ""))

        # Create CommentData objects
        comment_map: dict[str, CommentData] = {}
        for c in comments:
            comment_map[c["id"]] = CommentData(
                id=c["id"],
                author_name=c["author_name"],
                author_email=c["author_email"],
                content=c["content"],
                status=c["status"],
                created_at=c["created_at"],
            )

        # Build tree
        root_comments: list[CommentData] = []
        for c in comments:
            comment = comment_map[c["id"]]
            parent_id = c.get("parent_id")

            if parent_id and parent_id in comment_map:
                comment_map[parent_id].children.append(comment)
            else:
                root_comments.append(comment)

        return root_comments

    async def moderate(
        self,
        comment_id: str,
        action: str,
        user_id: str = None,
    ) -> bool:
        """
        Moderate a comment.

        Actions: approve, reject, spam
        """
        status_map = {
            "approve": "approved",
            "reject": "rejected",
            "spam": "spam",
        }

        new_status = status_map.get(action)
        if not new_status:
            return False

        entity = await self.entity_svc.get(comment_id)
        if not entity or entity.type != "comment":
            return False

        await self.entity_svc.update(
            comment_id,
            {"status": new_status},
            user_id=user_id,
            create_revision=False,
        )
        return True

    async def delete_comment(
        self,
        comment_id: str,
        user_id: str = None,
    ) -> bool:
        """Delete a comment (soft delete)."""
        return await self.entity_svc.delete(comment_id, user_id=user_id)

    async def get_pending_count(self) -> int:
        """Get count of pending comments."""
        from .entity import QueryParams

        params = QueryParams(filters={"status": "pending"})
        return await self.entity_svc.count("comment", params)

    async def get_recent_comments(
        self,
        limit: int = 10,
        status: str = None,
    ) -> list[dict[str, Any]]:
        """Get recent comments with post info."""
        filters = {}
        if status:
            filters["status"] = status

        comments = await self.entity_svc.find(
            "comment",
            limit=limit,
            order_by="-created_at",
            filters=filters,
        )

        result = []
        for c in comments:
            data = self.entity_svc.serialize(c)

            # Get related post
            post_relations = await self.relation_svc.get_relations(
                c.id, "comment_post", direction="from"
            )
            if post_relations:
                post = await self.entity_svc.get(post_relations[0].to_entity_id)
                if post:
                    post_data = self.entity_svc.serialize(post)
                    data["post_title"] = post_data.get("title", "")
                    data["post_slug"] = post_data.get("slug", "")

            result.append(data)

        return result

    async def _check_rate_limit(self, ip_address: str) -> bool:
        """Check if IP is within rate limit."""
        # Get recent comments from this IP
        cutoff = (utcnow() - timedelta(seconds=self.RATE_WINDOW)).isoformat()

        comments = await self.entity_svc.find(
            "comment",
            limit=self.RATE_LIMIT + 1,
            order_by="-created_at",
            filters={"ip_address": ip_address},
        )

        # Count comments within window
        count = 0
        for c in comments:
            data = self.entity_svc.serialize(c)
            created = data.get("created_at", "")
            if created and created >= cutoff:
                count += 1

        return count < self.RATE_LIMIT
