"""Plugin base classes and interfaces."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


class PluginState:
    """Plugin lifecycle states (string constants)."""

    UNKNOWN = "unknown"
    DISCOVERED = "discovered"
    LOADED = "loaded"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    ERROR = "error"
    INCOMPATIBLE = "incompatible"

    ALL = [UNKNOWN, DISCOVERED, LOADED, ACTIVATED, DEACTIVATED, ERROR, INCOMPATIBLE]


@dataclass
class PluginMeta:
    """Plugin metadata from manifest."""

    # Required
    id: str
    name: str
    version: str

    # Optional
    description: str = ""
    author: str = ""
    author_url: str = ""
    plugin_url: str = ""
    license: str = ""
    icon: str = ""
    category: str = "general"

    # Dependencies
    requires_focomy: str = ">=1.0.0"
    requires_python: str = ">=3.10"
    dependencies: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    # Capabilities
    admin_menu: bool = False
    settings_page: bool = False
    content_types: list[str] = field(default_factory=list)
    provides_hooks: list[str] = field(default_factory=list)
    uses_hooks: list[str] = field(default_factory=list)

    # Runtime info
    path: Path | None = None
    state: PluginState = PluginState.UNKNOWN
    error_message: str = ""
    loaded_at: datetime | None = None
    activated_at: datetime | None = None


class Plugin(ABC):
    """
    Base class for Focomy plugins.

    Plugins extend Focomy functionality through hooks and event handlers.
    Each plugin must inherit from this class and implement required methods.

    Example:
        class MyPlugin(Plugin):
            def activate(self):
                self.register_hook('content.before_save', self.on_before_save)

            def deactivate(self):
                pass

            def on_before_save(self, content):
                # Modify content before saving
                return content
    """

    def __init__(self, meta: PluginMeta, app: Any = None):
        """
        Initialize plugin.

        Args:
            meta: Plugin metadata
            app: Focomy application instance
        """
        self.meta = meta
        self.app = app
        self._hooks: list[tuple[str, Callable, int]] = []
        self._routes: list[tuple[str, str, Callable]] = []
        self._admin_menus: list[dict] = []
        self._settings: dict[str, Any] = {}

    @property
    def id(self) -> str:
        """Plugin identifier."""
        return self.meta.id

    @property
    def name(self) -> str:
        """Plugin display name."""
        return self.meta.name

    @property
    def version(self) -> str:
        """Plugin version."""
        return self.meta.version

    @property
    def path(self) -> Path | None:
        """Plugin directory path."""
        return self.meta.path

    @abstractmethod
    def activate(self) -> None:
        """
        Called when plugin is activated.

        Override this to register hooks, routes, and initialize resources.
        """
        pass

    @abstractmethod
    def deactivate(self) -> None:
        """
        Called when plugin is deactivated.

        Override this to cleanup resources and unregister handlers.
        """
        pass

    def install(self) -> None:
        """
        Called when plugin is first installed.

        Override for initial setup like creating database tables.
        """
        pass

    def uninstall(self) -> None:
        """
        Called when plugin is uninstalled.

        Override to cleanup all plugin data.
        """
        pass

    def upgrade(self, from_version: str) -> None:
        """
        Called when plugin is upgraded from a previous version.

        Args:
            from_version: Previous version string
        """
        pass

    def get_settings_schema(self) -> list[dict]:
        """
        Return settings schema for plugin configuration.

        Returns:
            List of field definitions for settings form
        """
        return []

    def get_settings(self) -> dict[str, Any]:
        """Get current plugin settings."""
        return self._settings.copy()

    def set_settings(self, settings: dict[str, Any]) -> None:
        """Update plugin settings."""
        self._settings.update(settings)

    def register_hook(
        self,
        hook_name: str,
        callback: Callable,
        priority: int = 10,
    ) -> None:
        """
        Register a hook handler.

        Args:
            hook_name: Name of the hook to handle
            callback: Function to call
            priority: Execution order (lower = earlier)
        """
        self._hooks.append((hook_name, callback, priority))

    def register_route(
        self,
        path: str,
        method: str,
        handler: Callable,
    ) -> None:
        """
        Register an HTTP route.

        Args:
            path: URL path (relative to plugin namespace)
            method: HTTP method (GET, POST, etc.)
            handler: Request handler function
        """
        self._routes.append((path, method, handler))

    def register_admin_menu(
        self,
        title: str,
        path: str,
        icon: str = "puzzle",
        parent: str | None = None,
    ) -> None:
        """
        Register an admin menu item.

        Args:
            title: Menu item title
            path: Route path for the menu
            icon: Icon name
            parent: Parent menu ID if submenu
        """
        self._admin_menus.append(
            {
                "title": title,
                "path": path,
                "icon": icon,
                "parent": parent,
                "plugin_id": self.id,
            }
        )

    def get_hooks(self) -> list[tuple[str, Callable, int]]:
        """Get all registered hooks."""
        return self._hooks.copy()

    def get_routes(self) -> list[tuple[str, str, Callable]]:
        """Get all registered routes."""
        return self._routes.copy()

    def get_admin_menus(self) -> list[dict]:
        """Get all registered admin menus."""
        return self._admin_menus.copy()

    def render_template(self, template_name: str, **context) -> str:
        """
        Render a plugin template.

        Args:
            template_name: Template file name
            **context: Template context variables

        Returns:
            Rendered HTML string
        """
        if not self.path:
            return ""

        from jinja2 import Environment, FileSystemLoader

        template_dir = self.path / "templates"
        if not template_dir.exists():
            return ""

        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template(template_name)
        return template.render(**context)

    def get_asset_url(self, asset_path: str) -> str:
        """
        Get URL for a plugin asset.

        Args:
            asset_path: Path relative to plugin assets directory

        Returns:
            Full URL to the asset
        """
        return f"/plugins/{self.id}/assets/{asset_path}"

    def log(self, message: str, level: str = "info") -> None:
        """
        Log a message from the plugin.

        Args:
            message: Log message
            level: Log level (debug, info, warning, error)
        """
        import logging

        logger = logging.getLogger(f"plugin.{self.id}")
        getattr(logger, level)(message)


class ContentTypePlugin(Plugin):
    """
    Base class for plugins that provide custom content types.

    Automatically registers content type definitions during activation.
    """

    def get_content_types(self) -> list[dict]:
        """
        Return content type definitions.

        Returns:
            List of content type configuration dicts
        """
        return []

    def activate(self) -> None:
        """Register content types on activation."""
        content_types = self.get_content_types()
        for ct_config in content_types:
            self.register_hook(
                "content_types.register",
                lambda: ct_config,
            )


class WidgetPlugin(Plugin):
    """
    Base class for plugins that provide dashboard widgets.
    """

    def get_widgets(self) -> list[dict]:
        """
        Return widget definitions.

        Returns:
            List of widget configuration dicts
        """
        return []

    def activate(self) -> None:
        """Register widgets on activation."""
        widgets = self.get_widgets()
        for widget in widgets:
            self.register_hook(
                "dashboard.widgets",
                lambda: widget,
            )


class ShortcodePlugin(Plugin):
    """
    Base class for plugins that provide content shortcodes.
    """

    def get_shortcodes(self) -> dict[str, Callable]:
        """
        Return shortcode handlers.

        Returns:
            Dict mapping shortcode names to handler functions
        """
        return {}

    def activate(self) -> None:
        """Register shortcodes on activation."""
        shortcodes = self.get_shortcodes()
        for name, handler in shortcodes.items():
            self.register_hook(
                f"shortcode.{name}",
                handler,
            )
