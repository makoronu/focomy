"""AuditService - Admin operation audit logging."""

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .entity import EntityService
from .logging import get_logger

logger = get_logger("focomy.audit")


class AuditService:
    """
    Audit logging service.

    Records admin operations for compliance and debugging.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.entity_svc = EntityService(db)

    async def log(
        self,
        action: str,
        user_id: str = None,
        user_email: str = None,
        user_name: str = None,
        entity_type: str = None,
        entity_id: str = None,
        entity_title: str = None,
        before_data: dict = None,
        after_data: dict = None,
        ip_address: str = None,
        user_agent: str = None,
        request_id: str = None,
        metadata: dict = None,
    ) -> None:
        """Log an admin operation.

        Args:
            action: The action performed (create, update, delete, login, etc.)
            user_id: ID of the user performing the action
            user_email: Email of the user
            user_name: Name of the user
            entity_type: Content type of the affected entity
            entity_id: ID of the affected entity
            entity_title: Title/name of the affected entity
            before_data: Data before the operation (for updates/deletes)
            after_data: Data after the operation (for creates/updates)
            ip_address: Client IP address
            user_agent: Client user agent
            request_id: Request tracking ID
            metadata: Additional context information
        """
        try:
            # Create audit log entry
            await self.entity_svc.create(
                "audit_log",
                {
                    "action": action,
                    "entity_type": entity_type or "",
                    "entity_id": entity_id or "",
                    "entity_title": entity_title or "",
                    "user_email": user_email or "",
                    "user_name": user_name or "",
                    "ip_address": ip_address or "",
                    "user_agent": (user_agent or "")[:500],  # Truncate long UA
                    "request_id": request_id or "",
                    "before_data": before_data,
                    "after_data": after_data,
                    "metadata": metadata,
                },
                user_id=user_id,
            )

            # Also log to structured logger for real-time monitoring
            logger.info(
                "Audit log entry",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                user_email=user_email,
                ip_address=ip_address,
                request_id=request_id,
            )

        except Exception as e:
            # Don't let audit logging failures break the main operation
            logger.error(
                "Failed to write audit log",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                error=str(e),
            )

    async def log_create(
        self,
        entity_type: str,
        entity_id: str,
        entity_title: str,
        data: dict,
        user_id: str = None,
        user_email: str = None,
        user_name: str = None,
        ip_address: str = None,
        user_agent: str = None,
        request_id: str = None,
    ) -> None:
        """Log an entity creation."""
        await self.log(
            action="create",
            user_id=user_id,
            user_email=user_email,
            user_name=user_name,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_title=entity_title,
            after_data=self._sanitize_data(data),
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )

    async def log_update(
        self,
        entity_type: str,
        entity_id: str,
        entity_title: str,
        before_data: dict,
        after_data: dict,
        user_id: str = None,
        user_email: str = None,
        user_name: str = None,
        ip_address: str = None,
        user_agent: str = None,
        request_id: str = None,
    ) -> None:
        """Log an entity update."""
        await self.log(
            action="update",
            user_id=user_id,
            user_email=user_email,
            user_name=user_name,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_title=entity_title,
            before_data=self._sanitize_data(before_data),
            after_data=self._sanitize_data(after_data),
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )

    async def log_delete(
        self,
        entity_type: str,
        entity_id: str,
        entity_title: str,
        data: dict,
        user_id: str = None,
        user_email: str = None,
        user_name: str = None,
        ip_address: str = None,
        user_agent: str = None,
        request_id: str = None,
    ) -> None:
        """Log an entity deletion."""
        await self.log(
            action="delete",
            user_id=user_id,
            user_email=user_email,
            user_name=user_name,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_title=entity_title,
            before_data=self._sanitize_data(data),
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )

    async def log_login(
        self,
        user_id: str,
        user_email: str,
        user_name: str = None,
        success: bool = True,
        ip_address: str = None,
        user_agent: str = None,
        request_id: str = None,
        failure_reason: str = None,
    ) -> None:
        """Log a login attempt."""
        await self.log(
            action="login" if success else "login_failed",
            user_id=user_id if success else None,
            user_email=user_email,
            user_name=user_name,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            metadata={"failure_reason": failure_reason} if failure_reason else None,
        )

    async def log_logout(
        self,
        user_id: str,
        user_email: str,
        user_name: str = None,
        ip_address: str = None,
        user_agent: str = None,
        request_id: str = None,
    ) -> None:
        """Log a logout."""
        await self.log(
            action="logout",
            user_id=user_id,
            user_email=user_email,
            user_name=user_name,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )

    async def log_settings_change(
        self,
        setting_key: str,
        before_value: Any,
        after_value: Any,
        user_id: str = None,
        user_email: str = None,
        user_name: str = None,
        ip_address: str = None,
        user_agent: str = None,
        request_id: str = None,
    ) -> None:
        """Log a settings change."""
        await self.log(
            action="settings_change",
            user_id=user_id,
            user_email=user_email,
            user_name=user_name,
            entity_type="site_setting",
            entity_id=setting_key,
            entity_title=setting_key,
            before_data={"value": before_value},
            after_data={"value": after_value},
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )

    async def find(
        self,
        action: str = None,
        entity_type: str = None,
        user_email: str = None,
        since: datetime = None,
        until: datetime = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Find audit log entries.

        Args:
            action: Filter by action type
            entity_type: Filter by entity type
            user_email: Filter by user email
            since: Filter entries after this time
            until: Filter entries before this time
            limit: Maximum number of entries to return
            offset: Number of entries to skip

        Returns:
            List of serialized audit log entries
        """
        filters = {}

        if action:
            filters["action"] = action
        if entity_type:
            filters["entity_type"] = entity_type
        if user_email:
            filters["user_email"] = user_email
        if since:
            filters["created_at"] = {"gte": since}
        if until:
            if "created_at" in filters:
                filters["created_at"]["lte"] = until
            else:
                filters["created_at"] = {"lte": until}

        entities = await self.entity_svc.find(
            "audit_log",
            limit=limit,
            offset=offset,
            order_by="-created_at",
            filters=filters if filters else None,
        )

        return [self.entity_svc.serialize(e) for e in entities]

    def _sanitize_data(self, data: dict) -> dict:
        """Remove sensitive fields from data before logging."""
        if not data:
            return data

        sanitized = data.copy()
        sensitive_fields = {
            "password",
            "password_hash",
            "token",
            "secret",
            "api_key",
            "access_token",
            "refresh_token",
            "reset_token",
            "totp_secret",
        }

        for key in list(sanitized.keys()):
            if key.lower() in sensitive_fields:
                sanitized[key] = "[REDACTED]"

        return sanitized


def get_client_ip(request) -> str:
    """Extract client IP from request, handling proxies."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def get_request_id(request) -> str:
    """Get request ID from request state."""
    return getattr(request.state, "request_id", "")
