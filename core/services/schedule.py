"""ScheduleService - scheduled publish/unpublish management."""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from .entity import EntityService


@dataclass
class ScheduledAction:
    """Scheduled action record."""

    id: str
    entity_id: str
    action_type: str  # publish, unpublish_archive, unpublish_draft, unpublish_delete
    scheduled_at: datetime
    created_by: str
    status: str  # pending, completed, cancelled, failed
    error_message: str | None = None
    completed_at: datetime | None = None


class ScheduleService:
    """
    Schedule management service.

    Handles scheduled publishing and unpublishing of content.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.entity_svc = EntityService(db)

    async def schedule_publish(
        self,
        entity_id: str,
        publish_at: datetime,
        user_id: str,
    ) -> str:
        """
        Schedule an entity for publishing.

        Args:
            entity_id: Entity to publish
            publish_at: When to publish
            user_id: User scheduling the action

        Returns:
            Scheduled action ID
        """
        # Cancel any existing publish schedule
        await self.cancel_scheduled(entity_id, "publish")

        # Create scheduled action entity
        action = await self.entity_svc.create(
            "scheduled_action",
            {
                "entity_id": entity_id,
                "action_type": "publish",
                "scheduled_at": publish_at.isoformat(),
                "status": "pending",
            },
            user_id=user_id,
        )

        return str(action.id)

    async def schedule_unpublish(
        self,
        entity_id: str,
        unpublish_at: datetime,
        user_id: str,
        action: str = "archive",  # archive, draft, delete
    ) -> str:
        """
        Schedule an entity for unpublishing.

        Args:
            entity_id: Entity to unpublish
            unpublish_at: When to unpublish
            user_id: User scheduling the action
            action: What to do (archive, draft, delete)

        Returns:
            Scheduled action ID
        """
        action_type = f"unpublish_{action}"

        # Cancel any existing unpublish schedule
        await self.cancel_scheduled(entity_id, action_type)

        # Create scheduled action entity
        scheduled = await self.entity_svc.create(
            "scheduled_action",
            {
                "entity_id": entity_id,
                "action_type": action_type,
                "scheduled_at": unpublish_at.isoformat(),
                "status": "pending",
            },
            user_id=user_id,
        )

        return str(scheduled.id)

    async def cancel_scheduled(self, entity_id: str, action_type: str) -> bool:
        """
        Cancel a scheduled action.

        Args:
            entity_id: Entity ID
            action_type: Type of action to cancel

        Returns:
            True if cancelled, False if not found
        """
        # Find pending actions
        actions = await self.entity_svc.find(
            "scheduled_action",
            limit=10,
            filters={
                "entity_id": entity_id,
                "action_type": action_type,
                "status": "pending",
            },
        )

        for action in actions:
            await self.entity_svc.update(
                action.id,
                {"status": "cancelled"},
            )

        return len(actions) > 0

    async def get_pending_actions(
        self,
        before: datetime = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get pending scheduled actions.

        Args:
            before: Only get actions scheduled before this time
            limit: Maximum number to return

        Returns:
            List of scheduled actions
        """
        filters = {"status": "pending"}

        actions = await self.entity_svc.find(
            "scheduled_action",
            limit=limit,
            order_by="scheduled_at",
            filters=filters,
        )

        result = []
        now = before or utcnow()

        for action in actions:
            data = self.entity_svc.serialize(action)
            scheduled_at = data.get("scheduled_at")

            if scheduled_at:
                if isinstance(scheduled_at, str):
                    scheduled_at = datetime.fromisoformat(scheduled_at.replace("Z", ""))

                if scheduled_at <= now:
                    result.append(data)

        return result

    async def get_scheduled_for_entity(self, entity_id: str) -> list[dict]:
        """Get all pending scheduled actions for an entity."""
        actions = await self.entity_svc.find(
            "scheduled_action",
            limit=10,
            filters={
                "entity_id": entity_id,
                "status": "pending",
            },
        )

        return [self.entity_svc.serialize(a) for a in actions]

    async def execute_action(self, action_id: str) -> tuple[bool, str]:
        """
        Execute a scheduled action.

        Args:
            action_id: Action to execute

        Returns:
            Tuple of (success, error_message)
        """
        action = await self.entity_svc.get(action_id)
        if not action:
            return False, "Action not found"

        data = self.entity_svc.serialize(action)
        entity_id = data.get("entity_id")
        action_type = data.get("action_type")
        status = data.get("status")

        if status != "pending":
            return False, f"Action is not pending (status: {status})"

        try:
            if action_type == "publish":
                await self._execute_publish(entity_id)
            elif action_type == "unpublish_archive":
                await self._execute_unpublish(entity_id, "archive")
            elif action_type == "unpublish_draft":
                await self._execute_unpublish(entity_id, "draft")
            elif action_type == "unpublish_delete":
                await self._execute_delete(entity_id)
            else:
                return False, f"Unknown action type: {action_type}"

            # Mark as completed
            await self.entity_svc.update(
                action_id,
                {
                    "status": "completed",
                    "completed_at": utcnow().isoformat(),
                },
            )

            return True, ""

        except Exception as e:
            # Mark as failed
            await self.entity_svc.update(
                action_id,
                {
                    "status": "failed",
                    "error_message": str(e),
                },
            )
            return False, str(e)

    async def _execute_publish(self, entity_id: str) -> None:
        """Execute publish action."""
        await self.entity_svc.update(
            entity_id,
            {
                "status": "published",
                "published_at": utcnow().isoformat(),
            },
        )

    async def _execute_unpublish(self, entity_id: str, action: str) -> None:
        """Execute unpublish action."""
        new_status = "archive" if action == "archive" else "draft"
        await self.entity_svc.update(
            entity_id,
            {"status": new_status},
        )

    async def _execute_delete(self, entity_id: str) -> None:
        """Execute delete action."""
        await self.entity_svc.delete(entity_id)

    async def process_due_actions(self) -> tuple[int, int]:
        """
        Process all due scheduled actions.

        Returns:
            Tuple of (processed_count, failed_count)
        """
        actions = await self.get_pending_actions()

        processed = 0
        failed = 0

        for action in actions:
            success, _ = await self.execute_action(action["id"])
            if success:
                processed += 1
            else:
                failed += 1

        return processed, failed
