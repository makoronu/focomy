"""Hook system for plugin extensibility."""

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class HookHandler:
    """Registered hook handler."""

    callback: Callable
    priority: int = 10
    plugin_id: str | None = None
    is_async: bool = False
    accepts_args: int = -1  # -1 means any


@dataclass
class HookResult:
    """Result of hook execution."""

    value: Any
    handlers_called: int = 0
    errors: list[str] = field(default_factory=list)


class HookRegistry:
    """
    Central registry for hooks (filters and actions).

    Hooks allow plugins to modify data (filters) or perform
    side effects (actions) at specific points in the application.

    Filter hooks:
        - Receive a value and return a modified value
        - Can be chained, each handler receives previous result
        - Example: content.before_save, template.context

    Action hooks:
        - Perform side effects, return value is ignored
        - All handlers are called in priority order
        - Example: content.saved, user.logged_in

    Usage:
        registry = HookRegistry()

        # Register a filter
        @registry.filter('content.before_save', priority=10)
        def modify_content(content):
            content['modified'] = True
            return content

        # Register an action
        @registry.action('content.saved')
        def on_content_saved(content):
            send_notification(content)

        # Apply filter
        content = registry.apply_filters('content.before_save', content)

        # Do action
        registry.do_action('content.saved', content)
    """

    def __init__(self):
        self._filters: dict[str, list[HookHandler]] = defaultdict(list)
        self._actions: dict[str, list[HookHandler]] = defaultdict(list)
        self._hook_docs: dict[str, str] = {}
        self._execution_count: dict[str, int] = defaultdict(int)

    def add_filter(
        self,
        hook_name: str,
        callback: Callable,
        priority: int = 10,
        plugin_id: str | None = None,
    ) -> None:
        """
        Register a filter handler.

        Args:
            hook_name: Name of the hook
            callback: Handler function
            priority: Execution order (lower = earlier)
            plugin_id: Optional plugin identifier
        """
        handler = HookHandler(
            callback=callback,
            priority=priority,
            plugin_id=plugin_id,
            is_async=asyncio.iscoroutinefunction(callback),
        )
        self._filters[hook_name].append(handler)
        self._filters[hook_name].sort(key=lambda h: h.priority)

    def add_action(
        self,
        hook_name: str,
        callback: Callable,
        priority: int = 10,
        plugin_id: str | None = None,
    ) -> None:
        """
        Register an action handler.

        Args:
            hook_name: Name of the hook
            callback: Handler function
            priority: Execution order (lower = earlier)
            plugin_id: Optional plugin identifier
        """
        handler = HookHandler(
            callback=callback,
            priority=priority,
            plugin_id=plugin_id,
            is_async=asyncio.iscoroutinefunction(callback),
        )
        self._actions[hook_name].append(handler)
        self._actions[hook_name].sort(key=lambda h: h.priority)

    def remove_filter(
        self,
        hook_name: str,
        callback: Callable | None = None,
        plugin_id: str | None = None,
    ) -> int:
        """
        Remove filter handler(s).

        Args:
            hook_name: Name of the hook
            callback: Specific callback to remove (or None for all)
            plugin_id: Remove all handlers from this plugin

        Returns:
            Number of handlers removed
        """
        return self._remove_handler(self._filters, hook_name, callback, plugin_id)

    def remove_action(
        self,
        hook_name: str,
        callback: Callable | None = None,
        plugin_id: str | None = None,
    ) -> int:
        """
        Remove action handler(s).

        Args:
            hook_name: Name of the hook
            callback: Specific callback to remove (or None for all)
            plugin_id: Remove all handlers from this plugin

        Returns:
            Number of handlers removed
        """
        return self._remove_handler(self._actions, hook_name, callback, plugin_id)

    def _remove_handler(
        self,
        registry: dict,
        hook_name: str,
        callback: Callable | None,
        plugin_id: str | None,
    ) -> int:
        """Remove handlers from a registry."""
        if hook_name not in registry:
            return 0

        original_count = len(registry[hook_name])

        if callback:
            registry[hook_name] = [h for h in registry[hook_name] if h.callback != callback]
        elif plugin_id:
            registry[hook_name] = [h for h in registry[hook_name] if h.plugin_id != plugin_id]
        else:
            registry[hook_name] = []

        return original_count - len(registry[hook_name])

    def apply_filters(self, hook_name: str, value: T, *args, **kwargs) -> T:
        """
        Apply all filter handlers to a value.

        Args:
            hook_name: Name of the hook
            value: Initial value to filter
            *args: Additional arguments passed to handlers
            **kwargs: Additional keyword arguments

        Returns:
            Filtered value
        """
        self._execution_count[hook_name] += 1

        handlers = self._filters.get(hook_name, [])
        if not handlers:
            return value

        for handler in handlers:
            try:
                if handler.is_async:
                    # Run async handler synchronously
                    loop = asyncio.get_event_loop()
                    value = loop.run_until_complete(handler.callback(value, *args, **kwargs))
                else:
                    value = handler.callback(value, *args, **kwargs)
            except Exception as e:
                logger.exception(
                    f"Error in filter '{hook_name}' handler " f"(plugin: {handler.plugin_id}): {e}"
                )

        return value

    async def apply_filters_async(
        self,
        hook_name: str,
        value: T,
        *args,
        **kwargs,
    ) -> T:
        """
        Apply all filter handlers asynchronously.

        Args:
            hook_name: Name of the hook
            value: Initial value to filter
            *args: Additional arguments passed to handlers
            **kwargs: Additional keyword arguments

        Returns:
            Filtered value
        """
        self._execution_count[hook_name] += 1

        handlers = self._filters.get(hook_name, [])
        if not handlers:
            return value

        for handler in handlers:
            try:
                if handler.is_async:
                    value = await handler.callback(value, *args, **kwargs)
                else:
                    value = handler.callback(value, *args, **kwargs)
            except Exception as e:
                logger.exception(
                    f"Error in filter '{hook_name}' handler " f"(plugin: {handler.plugin_id}): {e}"
                )

        return value

    def do_action(self, hook_name: str, *args, **kwargs) -> HookResult:
        """
        Execute all action handlers.

        Args:
            hook_name: Name of the hook
            *args: Arguments passed to handlers
            **kwargs: Keyword arguments

        Returns:
            HookResult with execution info
        """
        self._execution_count[hook_name] += 1

        result = HookResult(value=None)
        handlers = self._actions.get(hook_name, [])

        for handler in handlers:
            try:
                if handler.is_async:
                    loop = asyncio.get_event_loop()
                    loop.run_until_complete(handler.callback(*args, **kwargs))
                else:
                    handler.callback(*args, **kwargs)
                result.handlers_called += 1
            except Exception as e:
                error_msg = (
                    f"Error in action '{hook_name}' handler " f"(plugin: {handler.plugin_id}): {e}"
                )
                logger.exception(error_msg)
                result.errors.append(error_msg)

        return result

    async def do_action_async(self, hook_name: str, *args, **kwargs) -> HookResult:
        """
        Execute all action handlers asynchronously.

        Args:
            hook_name: Name of the hook
            *args: Arguments passed to handlers
            **kwargs: Keyword arguments

        Returns:
            HookResult with execution info
        """
        self._execution_count[hook_name] += 1

        result = HookResult(value=None)
        handlers = self._actions.get(hook_name, [])

        for handler in handlers:
            try:
                if handler.is_async:
                    await handler.callback(*args, **kwargs)
                else:
                    handler.callback(*args, **kwargs)
                result.handlers_called += 1
            except Exception as e:
                error_msg = (
                    f"Error in action '{hook_name}' handler " f"(plugin: {handler.plugin_id}): {e}"
                )
                logger.exception(error_msg)
                result.errors.append(error_msg)

        return result

    def has_filter(self, hook_name: str) -> bool:
        """Check if any filters are registered for a hook."""
        return bool(self._filters.get(hook_name))

    def has_action(self, hook_name: str) -> bool:
        """Check if any actions are registered for a hook."""
        return bool(self._actions.get(hook_name))

    def get_filters(self, hook_name: str) -> list[HookHandler]:
        """Get all filter handlers for a hook."""
        return self._filters.get(hook_name, []).copy()

    def get_actions(self, hook_name: str) -> list[HookHandler]:
        """Get all action handlers for a hook."""
        return self._actions.get(hook_name, []).copy()

    def document_hook(self, hook_name: str, description: str) -> None:
        """Add documentation for a hook."""
        self._hook_docs[hook_name] = description

    def get_hook_docs(self) -> dict[str, str]:
        """Get all hook documentation."""
        return self._hook_docs.copy()

    def get_all_hooks(self) -> dict[str, dict]:
        """Get information about all registered hooks."""
        all_hooks = set(self._filters.keys()) | set(self._actions.keys())

        return {
            hook_name: {
                "filters": len(self._filters.get(hook_name, [])),
                "actions": len(self._actions.get(hook_name, [])),
                "executions": self._execution_count.get(hook_name, 0),
                "description": self._hook_docs.get(hook_name, ""),
            }
            for hook_name in sorted(all_hooks)
        }

    def clear_plugin(self, plugin_id: str) -> None:
        """Remove all handlers registered by a plugin."""
        for hook_name in list(self._filters.keys()):
            self.remove_filter(hook_name, plugin_id=plugin_id)

        for hook_name in list(self._actions.keys()):
            self.remove_action(hook_name, plugin_id=plugin_id)

    def filter(
        self,
        hook_name: str,
        priority: int = 10,
    ) -> Callable:
        """
        Decorator for registering filter handlers.

        Usage:
            @hooks.filter('content.before_save')
            def modify_content(content):
                return content
        """

        def decorator(func: Callable) -> Callable:
            self.add_filter(hook_name, func, priority)
            return func

        return decorator

    def action(
        self,
        hook_name: str,
        priority: int = 10,
    ) -> Callable:
        """
        Decorator for registering action handlers.

        Usage:
            @hooks.action('content.saved')
            def on_saved(content):
                print(f"Saved: {content['id']}")
        """

        def decorator(func: Callable) -> Callable:
            self.add_action(hook_name, func, priority)
            return func

        return decorator


# Global hook registry
_global_registry = HookRegistry()


def hook(hook_name: str, priority: int = 10) -> Callable:
    """
    Decorator to register a hook handler (auto-detects filter vs action).

    Usage:
        @hook('content.before_save')
        def modify_content(content):
            return content
    """

    def decorator(func: Callable) -> Callable:
        # If function has a return annotation or returns something, treat as filter
        # Otherwise treat as action
        import inspect

        sig = inspect.signature(func)
        if sig.return_annotation != inspect.Parameter.empty:
            _global_registry.add_filter(hook_name, func, priority)
        else:
            _global_registry.add_action(hook_name, func, priority)
        return func

    return decorator


def filter_hook(hook_name: str, priority: int = 10) -> Callable:
    """Decorator to register a filter hook handler."""
    return _global_registry.filter(hook_name, priority)


def action_hook(hook_name: str, priority: int = 10) -> Callable:
    """Decorator to register an action hook handler."""
    return _global_registry.action(hook_name, priority)


def get_registry() -> HookRegistry:
    """Get the global hook registry."""
    return _global_registry


# Pre-defined hook names for documentation
CORE_HOOKS = {
    # Content hooks
    "content.before_save": "Called before content is saved. Filter receives content dict.",
    "content.after_save": "Called after content is saved. Action receives saved content.",
    "content.before_delete": "Called before content is deleted. Filter receives content.",
    "content.after_delete": "Called after content is deleted. Action receives content ID.",
    "content.before_publish": "Called before content is published. Filter receives content.",
    "content.after_publish": "Called after content is published. Action receives content.",
    # User hooks
    "user.before_login": "Called before user login attempt. Filter receives credentials.",
    "user.after_login": "Called after successful login. Action receives user.",
    "user.before_logout": "Called before user logout. Action receives user.",
    "user.after_register": "Called after user registration. Action receives new user.",
    # Template hooks
    "template.context": "Filter template context before rendering. Receives context dict.",
    "template.before_render": "Called before template rendering. Action receives template name.",
    "template.after_render": "Filter rendered HTML. Receives HTML string.",
    # Admin hooks
    "admin.menu": "Filter admin menu items. Receives menu list.",
    "admin.dashboard": "Filter dashboard widgets. Receives widget list.",
    "admin.before_action": "Called before admin action. Receives action info.",
    # API hooks
    "api.before_request": "Filter API request. Receives request object.",
    "api.after_response": "Filter API response. Receives response object.",
    # Media hooks
    "media.before_upload": "Called before file upload. Filter receives file info.",
    "media.after_upload": "Called after file upload. Action receives media record.",
    "media.before_delete": "Called before media deletion. Action receives media record.",
    # Search hooks
    "search.query": "Filter search query before execution. Receives query dict.",
    "search.results": "Filter search results. Receives results list.",
    # Email hooks
    "email.before_send": "Filter email before sending. Receives email dict.",
    "email.after_send": "Called after email sent. Action receives email info.",
    # Cache hooks
    "cache.before_get": "Called before cache get. Action receives cache key.",
    "cache.after_set": "Called after cache set. Action receives key and value.",
    "cache.clear": "Called when cache is cleared. Action receives pattern.",
}

# Register core hook documentation
for hook_name, description in CORE_HOOKS.items():
    _global_registry.document_hook(hook_name, description)
