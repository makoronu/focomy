"""EditLockService - concurrent edit prevention."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from .entity import EntityService


@dataclass
class EditLock:
    """Edit lock information."""

    entity_id: str
    user_id: str
    user_name: str
    acquired_at: datetime
    expires_at: datetime


class EditLockService:
    """
    Edit lock management service.

    Prevents concurrent editing of the same entity.
    Uses a timeout-based approach with automatic expiration.
    """

    LOCK_TIMEOUT_SECONDS = 300  # 5 minutes

    def __init__(self, db: AsyncSession):
        self.db = db
        self.entity_svc = EntityService(db)

    async def acquire_lock(
        self,
        entity_id: str,
        user_id: str,
        user_name: str = None,
    ) -> tuple[bool, EditLock | None]:
        """
        Try to acquire an edit lock.

        Args:
            entity_id: Entity to lock
            user_id: User requesting the lock
            user_name: Display name of the user

        Returns:
            Tuple of (success, existing_lock_if_failed)
        """
        # Check for existing lock
        existing = await self.get_lock(entity_id)

        if existing:
            # Check if expired
            if existing.expires_at < utcnow():
                # Lock expired, release it
                await self.release_lock(entity_id, existing.user_id)
            elif existing.user_id != user_id:
                # Someone else has the lock
                return False, existing
            else:
                # Same user, refresh the lock
                await self.refresh_lock(entity_id, user_id)
                return True, None

        # Create new lock
        now = utcnow()
        expires_at = now + timedelta(seconds=self.LOCK_TIMEOUT_SECONDS)

        await self.entity_svc.create(
            "edit_lock",
            {
                "entity_id": entity_id,
                "user_id": user_id,
                "user_name": user_name or user_id,
                "acquired_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            },
            user_id=user_id,
        )

        return True, None

    async def release_lock(self, entity_id: str, user_id: str) -> bool:
        """
        Release an edit lock.

        Args:
            entity_id: Entity to unlock
            user_id: User releasing the lock

        Returns:
            True if released, False if not found or not owned
        """
        locks = await self.entity_svc.find(
            "edit_lock",
            limit=1,
            filters={
                "entity_id": entity_id,
                "user_id": user_id,
            },
        )

        if locks:
            await self.entity_svc.delete(locks[0].id, hard=True)
            return True

        return False

    async def refresh_lock(self, entity_id: str, user_id: str) -> bool:
        """
        Refresh (extend) an edit lock.

        Args:
            entity_id: Entity with lock
            user_id: User with the lock

        Returns:
            True if refreshed, False if not found
        """
        locks = await self.entity_svc.find(
            "edit_lock",
            limit=1,
            filters={
                "entity_id": entity_id,
                "user_id": user_id,
            },
        )

        if locks:
            new_expires = utcnow() + timedelta(seconds=self.LOCK_TIMEOUT_SECONDS)
            await self.entity_svc.update(
                locks[0].id,
                {"expires_at": new_expires.isoformat()},
                user_id=user_id,
            )
            return True

        return False

    async def get_lock(self, entity_id: str) -> EditLock | None:
        """
        Get current lock for an entity.

        Args:
            entity_id: Entity to check

        Returns:
            EditLock if locked, None otherwise
        """
        locks = await self.entity_svc.find(
            "edit_lock",
            limit=1,
            filters={"entity_id": entity_id},
        )

        if not locks:
            return None

        data = self.entity_svc.serialize(locks[0])

        acquired_at = data.get("acquired_at")
        if isinstance(acquired_at, str):
            acquired_at = datetime.fromisoformat(acquired_at.replace("Z", ""))

        expires_at = data.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace("Z", ""))

        return EditLock(
            entity_id=data.get("entity_id", ""),
            user_id=data.get("user_id", ""),
            user_name=data.get("user_name", ""),
            acquired_at=acquired_at,
            expires_at=expires_at,
        )

    async def is_locked_by_other(
        self, entity_id: str, user_id: str
    ) -> tuple[bool, EditLock | None]:
        """
        Check if entity is locked by another user.

        Args:
            entity_id: Entity to check
            user_id: Current user

        Returns:
            Tuple of (is_locked_by_other, lock_info)
        """
        lock = await self.get_lock(entity_id)

        if not lock:
            return False, None

        # Check if expired
        if lock.expires_at < utcnow():
            return False, None

        # Check if same user
        if lock.user_id == user_id:
            return False, None

        return True, lock

    async def cleanup_expired(self) -> int:
        """
        Clean up expired locks.

        Returns:
            Number of locks cleaned up
        """
        locks = await self.entity_svc.find(
            "edit_lock",
            limit=1000,
        )

        now = utcnow()
        cleaned = 0

        for lock in locks:
            data = self.entity_svc.serialize(lock)
            expires_at = data.get("expires_at")

            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at.replace("Z", ""))

            if expires_at and expires_at < now:
                await self.entity_svc.delete(lock.id, hard=True)
                cleaned += 1

        return cleaned

    async def force_release(self, entity_id: str, admin_user_id: str) -> bool:
        """
        Force release a lock (admin action).

        Args:
            entity_id: Entity to unlock
            admin_user_id: Admin user performing the action

        Returns:
            True if released
        """
        locks = await self.entity_svc.find(
            "edit_lock",
            limit=1,
            filters={"entity_id": entity_id},
        )

        if locks:
            await self.entity_svc.delete(locks[0].id, hard=True)
            return True

        return False
