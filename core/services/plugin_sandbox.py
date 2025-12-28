"""Plugin Sandbox - Secure plugin execution environment.

Provides:
- Permission-based access control
- Resource limits
- Safe API exposure
"""

import os
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PluginPermissions:
    """Plugin permission set."""

    # Database access
    can_read_entities: bool = True
    can_write_entities: bool = False
    can_delete_entities: bool = False
    allowed_entity_types: set[str] = field(default_factory=set)  # Empty = all

    # File system access
    can_read_files: bool = False
    can_write_files: bool = False
    allowed_paths: set[str] = field(default_factory=set)

    # Network access
    can_make_requests: bool = False
    allowed_domains: set[str] = field(default_factory=set)

    # Admin features
    can_modify_settings: bool = False
    can_access_users: bool = False
    can_send_emails: bool = False

    # Resource limits
    max_memory_mb: int = 50
    max_execution_time_seconds: int = 30
    max_db_queries: int = 100


@dataclass
class ResourceUsage:
    """Track resource usage."""

    db_queries: int = 0
    start_time: float = 0
    memory_used_mb: float = 0


class PermissionDeniedError(Exception):
    """Raised when a plugin tries to access a restricted resource."""

    pass


class ResourceLimitError(Exception):
    """Raised when a plugin exceeds resource limits."""

    pass


class PluginSandbox:
    """
    Sandbox environment for plugin execution.

    Usage:
        sandbox = PluginSandbox(permissions)

        # Execute plugin code safely
        with sandbox.execute() as ctx:
            result = ctx.call(plugin_function, arg1, arg2)

        # Create safe API for plugins
        safe_api = sandbox.create_safe_api(entity_service)
    """

    def __init__(self, permissions: PluginPermissions):
        self.permissions = permissions
        self._usage = ResourceUsage()
        self._active = False

    @contextmanager
    def execute(self):
        """Context manager for sandboxed execution."""
        self._active = True
        self._usage = ResourceUsage(start_time=time.time())

        try:
            yield SandboxContext(self)
        finally:
            self._active = False

    def check_permission(self, permission: str, **context) -> bool:
        """Check if a specific permission is granted."""
        if permission == "read_entities":
            if not self.permissions.can_read_entities:
                return False
            entity_type = context.get("entity_type")
            if self.permissions.allowed_entity_types:
                return entity_type in self.permissions.allowed_entity_types
            return True

        elif permission == "write_entities":
            if not self.permissions.can_write_entities:
                return False
            entity_type = context.get("entity_type")
            if self.permissions.allowed_entity_types:
                return entity_type in self.permissions.allowed_entity_types
            return True

        elif permission == "delete_entities":
            return self.permissions.can_delete_entities

        elif permission == "read_files":
            if not self.permissions.can_read_files:
                return False
            path = context.get("path", "")
            return self._is_path_allowed(path)

        elif permission == "write_files":
            if not self.permissions.can_write_files:
                return False
            path = context.get("path", "")
            return self._is_path_allowed(path)

        elif permission == "make_requests":
            if not self.permissions.can_make_requests:
                return False
            domain = context.get("domain", "")
            if self.permissions.allowed_domains:
                return domain in self.permissions.allowed_domains
            return True

        elif permission == "modify_settings":
            return self.permissions.can_modify_settings

        elif permission == "access_users":
            return self.permissions.can_access_users

        elif permission == "send_emails":
            return self.permissions.can_send_emails

        return False

    def require_permission(self, permission: str, **context):
        """Require a permission or raise error."""
        if not self.check_permission(permission, **context):
            raise PermissionDeniedError(f"Permission denied: {permission}")

    def check_resource_limits(self):
        """Check if resource limits are exceeded."""
        # Check execution time
        elapsed = time.time() - self._usage.start_time
        if elapsed > self.permissions.max_execution_time_seconds:
            raise ResourceLimitError(
                f"Execution time limit exceeded: {elapsed:.1f}s > {self.permissions.max_execution_time_seconds}s"
            )

        # Check query count
        if self._usage.db_queries > self.permissions.max_db_queries:
            raise ResourceLimitError(
                f"Query limit exceeded: {self._usage.db_queries} > {self.permissions.max_db_queries}"
            )

    def record_db_query(self):
        """Record a database query."""
        self._usage.db_queries += 1
        self.check_resource_limits()

    def _is_path_allowed(self, path: str) -> bool:
        """Check if a file path is allowed."""
        if not self.permissions.allowed_paths:
            return False

        # Normalize path
        path = os.path.abspath(path)

        for allowed in self.permissions.allowed_paths:
            allowed = os.path.abspath(allowed)
            if path.startswith(allowed):
                return True

        return False

    def create_safe_api(self, entity_service, **services) -> "SafePluginAPI":
        """Create a safe API for plugins."""
        return SafePluginAPI(self, entity_service, **services)


class SandboxContext:
    """Context for sandboxed execution."""

    def __init__(self, sandbox: PluginSandbox):
        self.sandbox = sandbox

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Call a function within the sandbox."""
        self.sandbox.check_resource_limits()
        return func(*args, **kwargs)

    def check_permission(self, permission: str, **context) -> bool:
        """Check a permission."""
        return self.sandbox.check_permission(permission, **context)

    def require_permission(self, permission: str, **context):
        """Require a permission."""
        self.sandbox.require_permission(permission, **context)


class SafePluginAPI:
    """
    Safe API exposed to plugins.

    Wraps services with permission checks.
    """

    def __init__(
        self,
        sandbox: PluginSandbox,
        entity_service,
        **services,
    ):
        self._sandbox = sandbox
        self._entity_service = entity_service
        self._services = services

    async def get_entity(self, entity_id: str, entity_type: str = None):
        """Get an entity (with permission check)."""
        self._sandbox.require_permission("read_entities", entity_type=entity_type)
        self._sandbox.record_db_query()
        return await self._entity_service.get(entity_id)

    async def list_entities(
        self,
        entity_type: str,
        limit: int = 20,
        offset: int = 0,
    ):
        """List entities (with permission check)."""
        self._sandbox.require_permission("read_entities", entity_type=entity_type)
        self._sandbox.record_db_query()

        # Enforce reasonable limits
        limit = min(limit, 100)

        return await self._entity_service.list(entity_type, limit=limit, offset=offset)

    async def create_entity(self, entity_type: str, values: dict):
        """Create an entity (with permission check)."""
        self._sandbox.require_permission("write_entities", entity_type=entity_type)
        self._sandbox.record_db_query()
        return await self._entity_service.create(
            type_name=entity_type,
            values=values,
        )

    async def update_entity(self, entity_id: str, values: dict, entity_type: str = None):
        """Update an entity (with permission check)."""
        self._sandbox.require_permission("write_entities", entity_type=entity_type)
        self._sandbox.record_db_query()
        return await self._entity_service.update(entity_id, values)

    async def delete_entity(self, entity_id: str, entity_type: str = None):
        """Delete an entity (with permission check)."""
        self._sandbox.require_permission("delete_entities", entity_type=entity_type)
        self._sandbox.record_db_query()
        return await self._entity_service.delete(entity_id)

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value (read-only)."""
        settings_service = self._services.get("settings")
        if settings_service:
            return settings_service.get(key, default)
        return default

    async def log(self, level: str, message: str, **context):
        """Log a message from the plugin."""
        # Plugins can always log
        logger = self._services.get("logger")
        if logger:
            await logger.log(level, f"[Plugin] {message}", **context)


def create_permission_preset(preset: str) -> PluginPermissions:
    """Create a permission preset."""
    if preset == "minimal":
        return PluginPermissions(
            can_read_entities=True,
            can_write_entities=False,
            can_delete_entities=False,
        )

    elif preset == "standard":
        return PluginPermissions(
            can_read_entities=True,
            can_write_entities=True,
            can_delete_entities=False,
            can_make_requests=True,
        )

    elif preset == "trusted":
        return PluginPermissions(
            can_read_entities=True,
            can_write_entities=True,
            can_delete_entities=True,
            can_read_files=True,
            can_write_files=True,
            can_make_requests=True,
            can_modify_settings=True,
            can_send_emails=True,
            max_execution_time_seconds=60,
            max_db_queries=500,
        )

    # Default minimal
    return PluginPermissions()


def get_plugin_sandbox(permissions: PluginPermissions) -> PluginSandbox:
    return PluginSandbox(permissions)
