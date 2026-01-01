"""RBAC (Role-Based Access Control) Service.

Provides permission checking based on user roles and content types.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from .entity import EntityService


class Permission:
    """Available permissions (string constants)."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    PUBLISH = "publish"
    MANAGE_USERS = "manage_users"
    MANAGE_SETTINGS = "manage_settings"
    MANAGE_MEDIA = "manage_media"
    VIEW_AUDIT = "view_audit"

    ALL = [CREATE, READ, UPDATE, DELETE, PUBLISH, MANAGE_USERS, MANAGE_SETTINGS, MANAGE_MEDIA, VIEW_AUDIT]


class Role:
    """User roles with increasing privileges (string constants)."""

    AUTHOR = "author"
    EDITOR = "editor"
    ADMIN = "admin"

    ALL = [AUTHOR, EDITOR, ADMIN]


# Permission matrix: role -> content_type -> permissions
# "*" means all content types
PERMISSION_MATRIX: dict[str, dict[str, set[str]]] = {
    Role.AUTHOR: {
        # Authors can create/edit their own content
        "*": {Permission.CREATE, Permission.READ},
        "post": {Permission.CREATE, Permission.READ, Permission.UPDATE},
        "page": {Permission.READ},  # Read only for pages
        "comment": {Permission.CREATE, Permission.READ, Permission.UPDATE, Permission.DELETE},
        "media": {Permission.CREATE, Permission.READ},
        "user": set(),  # No access to users
        "audit_log": set(),  # No access to audit logs
        "site_setting": set(),  # No access to settings
    },
    Role.EDITOR: {
        # Editors can manage most content
        "*": {
            Permission.CREATE,
            Permission.READ,
            Permission.UPDATE,
            Permission.DELETE,
            Permission.PUBLISH,
        },
        "post": {
            Permission.CREATE,
            Permission.READ,
            Permission.UPDATE,
            Permission.DELETE,
            Permission.PUBLISH,
        },
        "page": {
            Permission.CREATE,
            Permission.READ,
            Permission.UPDATE,
            Permission.DELETE,
            Permission.PUBLISH,
        },
        "category": {Permission.CREATE, Permission.READ, Permission.UPDATE, Permission.DELETE},
        "tag": {Permission.CREATE, Permission.READ, Permission.UPDATE, Permission.DELETE},
        "comment": {Permission.CREATE, Permission.READ, Permission.UPDATE, Permission.DELETE},
        "media": {
            Permission.CREATE,
            Permission.READ,
            Permission.UPDATE,
            Permission.DELETE,
            Permission.MANAGE_MEDIA,
        },
        "user": {Permission.READ},  # Can view users
        "audit_log": set(),  # No access to audit logs
        "site_setting": set(),  # No access to settings
    },
    Role.ADMIN: {
        # Admins have full access
        "*": {
            Permission.CREATE,
            Permission.READ,
            Permission.UPDATE,
            Permission.DELETE,
            Permission.PUBLISH,
            Permission.MANAGE_USERS,
            Permission.MANAGE_SETTINGS,
            Permission.MANAGE_MEDIA,
            Permission.VIEW_AUDIT,
        },
    },
}

# Owner-only permissions: actions that require ownership
OWNER_ONLY_ACTIONS: dict[str, set[str]] = {
    Role.AUTHOR: {Permission.UPDATE, Permission.DELETE},
}


@dataclass
class PermissionResult:
    """Result of permission check."""

    allowed: bool
    reason: str | None = None
    requires_ownership: bool = False


class RBACService:
    """Role-Based Access Control service."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.entity_svc = EntityService(db)

    def get_role_permissions(
        self,
        role: str,
        content_type: str,
    ) -> set[str]:
        """Get all permissions for a role on a content type."""
        if role not in Role.ALL:
            return set()

        role_matrix = PERMISSION_MATRIX.get(role, {})

        # Check specific content type first
        if content_type in role_matrix:
            return role_matrix[content_type]

        # Fall back to wildcard
        return role_matrix.get("*", set())

    def has_permission(
        self,
        role: str,
        content_type: str,
        permission: str,
    ) -> bool:
        """Check if role has permission for content type."""
        permissions = self.get_role_permissions(role, content_type)
        return permission in permissions

    def check_permission(
        self,
        role: str,
        content_type: str,
        permission: str,
    ) -> PermissionResult:
        """Check permission and return detailed result."""
        if not self.has_permission(role, content_type, permission):
            return PermissionResult(
                allowed=False,
                reason=f"Role '{role}' does not have '{permission}' permission for '{content_type}'",
            )

        # Check if this requires ownership
        requires_ownership = (
            role in OWNER_ONLY_ACTIONS and permission in OWNER_ONLY_ACTIONS[role]
        )

        return PermissionResult(
            allowed=True,
            requires_ownership=requires_ownership,
        )

    async def can_access(
        self,
        user_id: str,
        content_type: str,
        permission: str,
        entity_id: str | None = None,
    ) -> PermissionResult:
        """Check if user can perform action, considering ownership."""
        # Get user role
        user = await self.entity_svc.get(user_id)
        if not user:
            return PermissionResult(allowed=False, reason="User not found")

        user_data = self.entity_svc.serialize(user)
        role = user_data.get("role", Role.AUTHOR)

        result = self.check_permission(role, content_type, permission)

        if not result.allowed:
            return result

        # If ownership is required, check it
        if result.requires_ownership and entity_id:
            entity = await self.entity_svc.get(entity_id)
            if not entity:
                return PermissionResult(allowed=False, reason="Entity not found")

            # Check if user owns the entity
            created_by = entity.created_by
            if created_by != user_id:
                return PermissionResult(
                    allowed=False,
                    reason="You can only modify your own content",
                )

        return PermissionResult(allowed=True)

    def get_allowed_types(self, role: str) -> list[str]:
        """Get list of content types the role can access."""
        if role not in Role.ALL:
            return []

        role_matrix = PERMISSION_MATRIX.get(role, {})

        # If admin, return all (indicated by only having "*")
        if role == Role.ADMIN:
            return ["*"]

        # Return types that have any permissions
        allowed = []
        for ct, perms in role_matrix.items():
            if ct != "*" and perms:
                allowed.append(ct)

        return allowed

    def get_menu_items(self, role: str, all_types: list[str]) -> list[str]:
        """Get content types that should appear in admin menu for role."""
        if role == Role.ADMIN:
            return all_types

        visible = []
        for ct in all_types:
            permissions = self.get_role_permissions(role, ct)
            if Permission.READ in permissions:
                visible.append(ct)

        return visible


# Convenience function for dependency injection
def get_rbac_service(db: AsyncSession) -> RBACService:
    return RBACService(db)
