"""Plugin Manager - Central management for the plugin system."""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import Plugin, PluginMeta, PluginState
from .hooks import HookRegistry, get_registry
from .loader import PluginLoader
from ..utils import utcnow

logger = logging.getLogger(__name__)


@dataclass
class PluginInfo:
    """Extended plugin information for admin UI."""

    meta: PluginMeta
    is_active: bool = False
    can_activate: bool = True
    activation_error: str = ""
    settings: dict = None
    stats: dict = None


class PluginManager:
    """
    Central plugin management system.

    Handles:
    - Plugin discovery and loading
    - Activation and deactivation
    - Settings persistence
    - Hook integration
    - Hot reload
    - Admin UI integration
    """

    def __init__(
        self,
        plugin_dirs: list[Path],
        data_dir: Path,
        app: Any = None,
        hook_registry: HookRegistry | None = None,
    ):
        """
        Initialize plugin manager.

        Args:
            plugin_dirs: Directories to scan for plugins
            data_dir: Directory for plugin data and settings
            app: Focomy application instance
            hook_registry: Hook registry (uses global if not provided)
        """
        self.plugin_dirs = [Path(d) for d in plugin_dirs]
        self.data_dir = Path(data_dir)
        self.app = app
        self.hooks = hook_registry or get_registry()

        self._loader = PluginLoader(plugin_dirs)
        self._active_plugins: set[str] = set()
        self._settings: dict[str, dict] = {}

        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._settings_file = self.data_dir / "plugin_settings.json"
        self._state_file = self.data_dir / "plugin_state.json"

        # Load persisted state
        self._load_state()

    def discover_all(self) -> dict[str, PluginMeta]:
        """
        Discover all available plugins.

        Returns:
            Dict of plugin IDs to metadata
        """
        return self._loader.discover()

    def get_all_plugins(self) -> list[PluginInfo]:
        """
        Get information about all plugins.

        Returns:
            List of PluginInfo for all discovered plugins
        """
        discovered = self._loader.get_all_discovered()
        result = []

        for plugin_id, meta in discovered.items():
            # Check activation requirements
            can_activate = True
            activation_error = ""

            deps_ok, missing = self._loader.check_dependencies(plugin_id)
            if not deps_ok:
                can_activate = False
                activation_error = f"Missing dependencies: {', '.join(missing)}"

            conflicts_ok, conflicts = self._loader.check_conflicts(plugin_id)
            if not conflicts_ok:
                can_activate = False
                activation_error = f"Conflicts with: {', '.join(conflicts)}"

            info = PluginInfo(
                meta=meta,
                is_active=plugin_id in self._active_plugins,
                can_activate=can_activate,
                activation_error=activation_error,
                settings=self._settings.get(plugin_id, {}),
                stats=self._get_plugin_stats(plugin_id),
            )
            result.append(info)

        return result

    def get_plugin(self, plugin_id: str) -> Plugin | None:
        """
        Get a loaded plugin instance.

        Args:
            plugin_id: Plugin identifier

        Returns:
            Plugin instance or None
        """
        return self._loader.get_loaded(plugin_id)

    def is_active(self, plugin_id: str) -> bool:
        """Check if a plugin is active."""
        return plugin_id in self._active_plugins

    async def activate(self, plugin_id: str) -> tuple[bool, str]:
        """
        Activate a plugin.

        Args:
            plugin_id: Plugin identifier

        Returns:
            Tuple of (success, message)
        """
        # Check if already active
        if plugin_id in self._active_plugins:
            return True, "Plugin already active"

        # Check dependencies
        deps_ok, missing = self._loader.check_dependencies(plugin_id)
        if not deps_ok:
            return False, f"Missing dependencies: {', '.join(missing)}"

        # Check conflicts
        conflicts_ok, conflicts = self._loader.check_conflicts(plugin_id)
        if not conflicts_ok:
            return False, f"Conflicts with active plugins: {', '.join(conflicts)}"

        # Load plugin if not loaded
        plugin = self._loader.get_loaded(plugin_id)
        if not plugin:
            plugin = self._loader.load(plugin_id, self.app)
            if not plugin:
                return False, "Failed to load plugin"

        try:
            # Run activation
            plugin.activate()

            # Register plugin hooks
            for hook_name, callback, priority in plugin.get_hooks():
                self.hooks.add_filter(hook_name, callback, priority, plugin_id)

            # Mark as active
            self._active_plugins.add(plugin_id)
            plugin.meta.state = PluginState.ACTIVATED
            plugin.meta.activated_at = utcnow()

            # Save state
            self._save_state()

            # Trigger activation hook
            self.hooks.do_action("plugin.activated", plugin_id, plugin)

            logger.info(f"Activated plugin: {plugin_id}")
            return True, "Plugin activated successfully"

        except Exception as e:
            logger.exception(f"Error activating plugin {plugin_id}: {e}")
            plugin.meta.state = PluginState.ERROR
            plugin.meta.error_message = str(e)
            return False, f"Activation error: {e}"

    async def deactivate(self, plugin_id: str) -> tuple[bool, str]:
        """
        Deactivate a plugin.

        Args:
            plugin_id: Plugin identifier

        Returns:
            Tuple of (success, message)
        """
        if plugin_id not in self._active_plugins:
            return True, "Plugin already inactive"

        plugin = self._loader.get_loaded(plugin_id)
        if not plugin:
            self._active_plugins.discard(plugin_id)
            return True, "Plugin not loaded"

        try:
            # Run deactivation
            plugin.deactivate()

            # Remove plugin hooks
            self.hooks.clear_plugin(plugin_id)

            # Mark as inactive
            self._active_plugins.discard(plugin_id)
            plugin.meta.state = PluginState.DEACTIVATED

            # Save state
            self._save_state()

            # Trigger deactivation hook
            self.hooks.do_action("plugin.deactivated", plugin_id, plugin)

            logger.info(f"Deactivated plugin: {plugin_id}")
            return True, "Plugin deactivated successfully"

        except Exception as e:
            logger.exception(f"Error deactivating plugin {plugin_id}: {e}")
            return False, f"Deactivation error: {e}"

    async def install(self, plugin_id: str) -> tuple[bool, str]:
        """
        Install a plugin (first-time setup).

        Args:
            plugin_id: Plugin identifier

        Returns:
            Tuple of (success, message)
        """
        plugin = self._loader.get_loaded(plugin_id)
        if not plugin:
            plugin = self._loader.load(plugin_id, self.app)
            if not plugin:
                return False, "Failed to load plugin"

        try:
            plugin.install()
            self.hooks.do_action("plugin.installed", plugin_id, plugin)
            logger.info(f"Installed plugin: {plugin_id}")
            return True, "Plugin installed successfully"
        except Exception as e:
            logger.exception(f"Error installing plugin {plugin_id}: {e}")
            return False, f"Installation error: {e}"

    async def uninstall(self, plugin_id: str) -> tuple[bool, str]:
        """
        Uninstall a plugin (cleanup all data).

        Args:
            plugin_id: Plugin identifier

        Returns:
            Tuple of (success, message)
        """
        # Deactivate first
        if plugin_id in self._active_plugins:
            await self.deactivate(plugin_id)

        plugin = self._loader.get_loaded(plugin_id)
        if plugin:
            try:
                plugin.uninstall()
            except Exception as e:
                logger.exception(f"Error in plugin uninstall: {e}")

        # Remove settings
        self._settings.pop(plugin_id, None)
        self._save_settings()

        # Unload
        self._loader.unload(plugin_id)

        self.hooks.do_action("plugin.uninstalled", plugin_id)
        logger.info(f"Uninstalled plugin: {plugin_id}")
        return True, "Plugin uninstalled successfully"

    async def reload(self, plugin_id: str) -> tuple[bool, str]:
        """
        Hot reload a plugin.

        Args:
            plugin_id: Plugin identifier

        Returns:
            Tuple of (success, message)
        """
        was_active = plugin_id in self._active_plugins

        if was_active:
            success, msg = await self.deactivate(plugin_id)
            if not success:
                return False, f"Failed to deactivate for reload: {msg}"

        # Reload module
        plugin = self._loader.reload(plugin_id, self.app)
        if not plugin:
            return False, "Failed to reload plugin"

        if was_active:
            success, msg = await self.activate(plugin_id)
            if not success:
                return False, f"Failed to reactivate after reload: {msg}"

        logger.info(f"Reloaded plugin: {plugin_id}")
        return True, "Plugin reloaded successfully"

    def get_settings(self, plugin_id: str) -> dict:
        """Get plugin settings."""
        return self._settings.get(plugin_id, {}).copy()

    def set_settings(self, plugin_id: str, settings: dict) -> None:
        """Update plugin settings."""
        self._settings[plugin_id] = settings

        # Update plugin instance
        plugin = self._loader.get_loaded(plugin_id)
        if plugin:
            plugin.set_settings(settings)

        self._save_settings()

    def get_settings_schema(self, plugin_id: str) -> list[dict]:
        """Get settings schema for a plugin."""
        plugin = self._loader.get_loaded(plugin_id)
        if plugin:
            return plugin.get_settings_schema()
        return []

    def get_admin_menus(self) -> list[dict]:
        """Get all admin menu items from active plugins."""
        menus = []
        for plugin_id in self._active_plugins:
            plugin = self._loader.get_loaded(plugin_id)
            if plugin:
                menus.extend(plugin.get_admin_menus())
        return menus

    def get_routes(self) -> list[tuple[str, str, str, Callable]]:
        """
        Get all routes from active plugins.

        Returns:
            List of (plugin_id, path, method, handler)
        """
        routes = []
        for plugin_id in self._active_plugins:
            plugin = self._loader.get_loaded(plugin_id)
            if plugin:
                for path, method, handler in plugin.get_routes():
                    routes.append((plugin_id, path, method, handler))
        return routes

    async def startup(self) -> None:
        """
        Initialize plugin system on application startup.

        Discovers plugins and activates previously active ones.
        """
        logger.info("Starting plugin system...")

        # Discover all plugins
        discovered = self.discover_all()
        logger.info(f"Discovered {len(discovered)} plugins")

        # Load and activate previously active plugins
        for plugin_id in list(self._active_plugins):
            if plugin_id in discovered:
                success, msg = await self.activate(plugin_id)
                if not success:
                    logger.warning(f"Failed to activate {plugin_id}: {msg}")
                    self._active_plugins.discard(plugin_id)
            else:
                logger.warning(f"Previously active plugin not found: {plugin_id}")
                self._active_plugins.discard(plugin_id)

        self._save_state()
        logger.info(f"Plugin system started with {len(self._active_plugins)} active plugins")

    async def shutdown(self) -> None:
        """
        Shutdown plugin system.

        Deactivates all plugins gracefully.
        """
        logger.info("Shutting down plugin system...")

        for plugin_id in list(self._active_plugins):
            plugin = self._loader.get_loaded(plugin_id)
            if plugin:
                try:
                    plugin.deactivate()
                except Exception as e:
                    logger.exception(f"Error deactivating {plugin_id}: {e}")

        self._save_state()
        logger.info("Plugin system shutdown complete")

    def _load_state(self) -> None:
        """Load plugin state from file."""
        if self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text())
                self._active_plugins = set(data.get("active_plugins", []))
            except Exception as e:
                logger.warning(f"Failed to load plugin state: {e}")
                self._active_plugins = set()

        if self._settings_file.exists():
            try:
                self._settings = json.loads(self._settings_file.read_text())
            except Exception as e:
                logger.warning(f"Failed to load plugin settings: {e}")
                self._settings = {}

    def _save_state(self) -> None:
        """Save plugin state to file."""
        try:
            data = {
                "active_plugins": list(self._active_plugins),
                "updated_at": utcnow().isoformat(),
            }
            self._state_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.exception(f"Failed to save plugin state: {e}")

    def _save_settings(self) -> None:
        """Save plugin settings to file."""
        try:
            self._settings_file.write_text(json.dumps(self._settings, indent=2))
        except Exception as e:
            logger.exception(f"Failed to save plugin settings: {e}")

    def _get_plugin_stats(self, plugin_id: str) -> dict:
        """Get statistics for a plugin."""
        # Count hooks registered by this plugin
        all_hooks = self.hooks.get_all_hooks()
        hook_count = 0

        for hook_name, _info in all_hooks.items():
            filters = self.hooks.get_filters(hook_name)
            actions = self.hooks.get_actions(hook_name)

            for handler in filters + actions:
                if handler.plugin_id == plugin_id:
                    hook_count += 1

        plugin = self._loader.get_loaded(plugin_id)
        route_count = len(plugin.get_routes()) if plugin else 0
        menu_count = len(plugin.get_admin_menus()) if plugin else 0

        return {
            "hooks_registered": hook_count,
            "routes_registered": route_count,
            "menus_registered": menu_count,
        }


# Convenience function for creating plugin manager
def create_plugin_manager(
    plugin_dirs: list[str],
    data_dir: str,
    app: Any = None,
) -> PluginManager:
    """
    Create a plugin manager with default settings.

    Args:
        plugin_dirs: Plugin directories
        data_dir: Data directory
        app: Application instance

    Returns:
        Configured PluginManager
    """
    return PluginManager(
        plugin_dirs=[Path(d) for d in plugin_dirs],
        data_dir=Path(data_dir),
        app=app,
    )
