"""WorkflowService - approval workflow management."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..utils import utcnow
from .entity import EntityService


@dataclass
class WorkflowState:
    """Workflow state definition."""

    name: str
    label: str
    color: str = "gray"
    initial: bool = False
    final: bool = False


@dataclass
class WorkflowTransition:
    """Workflow transition definition."""

    from_state: str
    to_state: str
    label: str
    permissions: list[str] = field(default_factory=list)
    require_comment: bool = False
    actions: list[dict] = field(default_factory=list)


@dataclass
class WorkflowDefinition:
    """Complete workflow definition."""

    name: str
    label: str
    description: str = ""
    states: list[WorkflowState] = field(default_factory=list)
    transitions: list[WorkflowTransition] = field(default_factory=list)

    @property
    def initial_state(self) -> str | None:
        """Get the initial state name."""
        for state in self.states:
            if state.initial:
                return state.name
        return self.states[0].name if self.states else None

    def get_state(self, name: str) -> WorkflowState | None:
        """Get state by name."""
        for state in self.states:
            if state.name == name:
                return state
        return None

    def get_transition(self, from_state: str, to_state: str) -> WorkflowTransition | None:
        """Get transition between states."""
        for t in self.transitions:
            if t.from_state == from_state and t.to_state == to_state:
                return t
        return None

    def get_available_transitions(self, current_state: str) -> list[WorkflowTransition]:
        """Get all transitions from current state."""
        return [t for t in self.transitions if t.from_state == current_state]


@dataclass
class WorkflowHistoryEntry:
    """Workflow history entry."""

    entity_id: str
    from_state: str
    to_state: str
    user_id: str
    comment: str | None
    created_at: datetime


class WorkflowService:
    """
    Workflow management service.

    Handles state transitions, permission checks, and history tracking.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.entity_svc = EntityService(db)
        self._workflows: dict[str, WorkflowDefinition] = {}
        self._loaded = False

    async def _load_workflows(self) -> None:
        """Load workflow definitions from YAML files."""
        if self._loaded:
            return

        workflows_dir = settings.base_dir / "workflows"
        if workflows_dir.exists():
            for path in workflows_dir.glob("*.yaml"):
                wf = self._load_workflow(path)
                if wf:
                    self._workflows[wf.name] = wf

        self._loaded = True

    def _load_workflow(self, path: Path) -> WorkflowDefinition | None:
        """Load a single workflow from YAML."""
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if not data:
                return None

            states = []
            for s in data.get("states", []):
                states.append(
                    WorkflowState(
                        name=s.get("name", ""),
                        label=s.get("label", s.get("name", "")),
                        color=s.get("color", "gray"),
                        initial=s.get("initial", False),
                        final=s.get("final", False),
                    )
                )

            transitions = []
            for t in data.get("transitions", []):
                transitions.append(
                    WorkflowTransition(
                        from_state=t.get("from", ""),
                        to_state=t.get("to", ""),
                        label=t.get("label", ""),
                        permissions=t.get("permissions", []),
                        require_comment=t.get("require_comment", False),
                        actions=t.get("actions", []),
                    )
                )

            return WorkflowDefinition(
                name=data.get("name", path.stem),
                label=data.get("label", data.get("name", path.stem)),
                description=data.get("description", ""),
                states=states,
                transitions=transitions,
            )

        except Exception as e:
            print(f"Error loading workflow {path}: {e}")
            return None

    async def get_workflow(self, name: str) -> WorkflowDefinition | None:
        """Get workflow definition by name."""
        await self._load_workflows()
        return self._workflows.get(name)

    async def get_all_workflows(self) -> dict[str, WorkflowDefinition]:
        """Get all workflow definitions."""
        await self._load_workflows()
        return self._workflows.copy()

    async def get_entity_state(self, entity_id: str) -> str | None:
        """Get current workflow state of an entity."""
        entity = await self.entity_svc.get(entity_id)
        if not entity:
            return None

        data = self.entity_svc.serialize(entity)
        return data.get("workflow_state")

    async def transition(
        self,
        entity_id: str,
        to_state: str,
        user_id: str,
        comment: str = None,
        user_roles: list[str] = None,
    ) -> tuple[bool, str]:
        """
        Execute a workflow transition.

        Args:
            entity_id: Entity to transition
            to_state: Target state
            user_id: User performing the transition
            comment: Optional comment
            user_roles: User's roles for permission check

        Returns:
            Tuple of (success, error_message)
        """
        entity = await self.entity_svc.get(entity_id)
        if not entity:
            return False, "Entity not found"

        data = self.entity_svc.serialize(entity)
        content_type = entity.type

        # Get workflow for content type
        # (You'd typically store workflow name on the content type definition)
        workflow_name = data.get("_workflow")
        if not workflow_name:
            # Default workflow based on content type
            workflow_name = f"{content_type}_workflow"

        workflow = await self.get_workflow(workflow_name)
        if not workflow:
            # Try generic content review workflow
            workflow = await self.get_workflow("content_review")
            if not workflow:
                return False, "Workflow not found"

        # Get current state
        current_state = data.get("workflow_state")
        if not current_state:
            current_state = workflow.initial_state

        # Find transition
        transition = workflow.get_transition(current_state, to_state)
        if not transition:
            return False, f"Cannot transition from {current_state} to {to_state}"

        # Check permissions
        if transition.permissions and user_roles:
            has_permission = any(r in transition.permissions for r in user_roles)
            if not has_permission:
                return False, "Permission denied for this transition"

        # Check required comment
        if transition.require_comment and not comment:
            return False, "Comment is required for this transition"

        # Execute transition
        await self.entity_svc.update(
            entity_id,
            {"workflow_state": to_state},
            user_id=user_id,
        )

        # Record history
        await self._record_history(entity_id, current_state, to_state, user_id, comment)

        # Execute actions
        for action in transition.actions:
            await self._execute_action(action, entity_id, user_id, comment)

        return True, ""

    async def get_available_transitions(
        self,
        entity_id: str,
        user_roles: list[str] = None,
    ) -> list[WorkflowTransition]:
        """
        Get available transitions for an entity.

        Args:
            entity_id: Entity ID
            user_roles: User's roles for filtering

        Returns:
            List of available transitions
        """
        entity = await self.entity_svc.get(entity_id)
        if not entity:
            return []

        data = self.entity_svc.serialize(entity)
        content_type = entity.type

        # Get workflow
        workflow_name = data.get("_workflow", f"{content_type}_workflow")
        workflow = await self.get_workflow(workflow_name)
        if not workflow:
            workflow = await self.get_workflow("content_review")
            if not workflow:
                return []

        current_state = data.get("workflow_state", workflow.initial_state)
        all_transitions = workflow.get_available_transitions(current_state)

        # Filter by permissions
        if user_roles:
            return [
                t
                for t in all_transitions
                if not t.permissions or any(r in t.permissions for r in user_roles)
            ]

        return all_transitions

    async def get_history(
        self,
        entity_id: str,
        limit: int = 50,
    ) -> list[dict]:
        """Get workflow history for an entity."""
        # Query from workflow_history content type
        histories = await self.entity_svc.find(
            "workflow_history",
            limit=limit,
            order_by="-created_at",
            filters={"entity_id": entity_id},
        )

        return [self.entity_svc.serialize(h) for h in histories]

    async def _record_history(
        self,
        entity_id: str,
        from_state: str,
        to_state: str,
        user_id: str,
        comment: str = None,
    ) -> None:
        """Record a workflow transition in history."""
        # Create workflow_history entity
        await self.entity_svc.create(
            "workflow_history",
            {
                "entity_id": entity_id,
                "from_state": from_state,
                "to_state": to_state,
                "comment": comment or "",
            },
            user_id=user_id,
        )

    async def _execute_action(
        self,
        action: dict,
        entity_id: str,
        user_id: str,
        comment: str = None,
    ) -> None:
        """Execute a workflow action."""
        action_type = action.get("type")

        if action_type == "set_field":
            # Set a field value
            field_name = action.get("field")
            value = action.get("value")

            if value == "now":
                value = utcnow().isoformat()

            await self.entity_svc.update(
                entity_id,
                {field_name: value},
                user_id=user_id,
            )

        elif action_type == "notify":
            # Send notification (placeholder - integrate with notification service)
            action.get("to")
            message = action.get("message", "")
            if comment:
                message = message.replace("{comment}", comment)
            # TODO: Integrate with notification service
            pass

        elif action_type == "webhook":
            # Call webhook (placeholder)
            action.get("url")
            # TODO: Implement webhook call
            pass


# Default workflow for content
DEFAULT_CONTENT_WORKFLOW = """
name: content_review
label: コンテンツレビュー
description: 投稿の承認フロー

states:
  - name: draft
    label: 下書き
    initial: true
    color: gray

  - name: pending_review
    label: レビュー待ち
    color: yellow

  - name: in_review
    label: レビュー中
    color: blue

  - name: approved
    label: 承認済み
    color: green

  - name: rejected
    label: 却下
    color: red

  - name: published
    label: 公開中
    final: true
    color: green

transitions:
  - from: draft
    to: pending_review
    label: レビュー依頼
    permissions: [author, editor, admin]

  - from: pending_review
    to: in_review
    label: レビュー開始
    permissions: [editor, admin]

  - from: in_review
    to: approved
    label: 承認
    permissions: [editor, admin]
    actions:
      - type: notify
        to: author
        message: 投稿が承認されました

  - from: in_review
    to: rejected
    label: 却下
    permissions: [editor, admin]
    require_comment: true
    actions:
      - type: notify
        to: author
        message: "投稿が却下されました: {comment}"

  - from: rejected
    to: draft
    label: 修正
    permissions: [author, editor, admin]

  - from: approved
    to: published
    label: 公開
    permissions: [editor, admin]
    actions:
      - type: set_field
        field: published_at
        value: now

  - from: published
    to: draft
    label: 非公開に戻す
    permissions: [admin]
"""
