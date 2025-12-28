"""Plugin loader - discovers and loads plugins from filesystem."""

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

import yaml

from .base import Plugin, PluginMeta, PluginState

logger = logging.getLogger(__name__)


class PluginLoader:
    """
    Discovers and loads plugins from the filesystem.

    Plugins are expected to have the following structure:
        plugins/
            my-plugin/
                manifest.yaml    # Plugin metadata
                plugin.py        # Main plugin class
                templates/       # Optional templates
                assets/          # Optional static assets
                migrations/      # Optional database migrations
    """

    def __init__(self, plugin_dirs: list[Path]):
        """
        Initialize plugin loader.

        Args:
            plugin_dirs: List of directories to scan for plugins
        """
        self.plugin_dirs = [Path(d) for d in plugin_dirs]
        self._discovered: dict[str, PluginMeta] = {}
        self._loaded: dict[str, Plugin] = {}

    def discover(self) -> dict[str, PluginMeta]:
        """
        Discover all plugins in configured directories.

        Returns:
            Dict mapping plugin IDs to their metadata
        """
        self._discovered = {}

        for plugin_dir in self.plugin_dirs:
            if not plugin_dir.exists():
                logger.warning(f"Plugin directory not found: {plugin_dir}")
                continue

            for item in plugin_dir.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    meta = self._discover_plugin(item)
                    if meta:
                        self._discovered[meta.id] = meta

        return self._discovered

    def _discover_plugin(self, path: Path) -> PluginMeta | None:
        """
        Discover a single plugin from its directory.

        Args:
            path: Path to plugin directory

        Returns:
            PluginMeta if valid plugin, None otherwise
        """
        manifest_file = path / "manifest.yaml"

        # Check for manifest
        if not manifest_file.exists():
            # Try manifest.yml
            manifest_file = path / "manifest.yml"
            if not manifest_file.exists():
                return None

        try:
            manifest = yaml.safe_load(manifest_file.read_text())

            # Validate required fields
            if not manifest.get("id"):
                logger.warning(f"Plugin at {path} missing 'id' in manifest")
                return None

            if not manifest.get("name"):
                manifest["name"] = manifest["id"]

            if not manifest.get("version"):
                manifest["version"] = "0.0.0"

            meta = PluginMeta(
                id=manifest["id"],
                name=manifest["name"],
                version=manifest["version"],
                description=manifest.get("description", ""),
                author=manifest.get("author", ""),
                author_url=manifest.get("author_url", ""),
                plugin_url=manifest.get("plugin_url", ""),
                license=manifest.get("license", ""),
                icon=manifest.get("icon", ""),
                category=manifest.get("category", "general"),
                requires_focomy=manifest.get("requires_focomy", ">=1.0.0"),
                requires_python=manifest.get("requires_python", ">=3.10"),
                dependencies=manifest.get("dependencies", []),
                conflicts=manifest.get("conflicts", []),
                admin_menu=manifest.get("admin_menu", False),
                settings_page=manifest.get("settings_page", False),
                content_types=manifest.get("content_types", []),
                provides_hooks=manifest.get("provides_hooks", []),
                uses_hooks=manifest.get("uses_hooks", []),
                path=path,
                state=PluginState.DISCOVERED,
            )

            return meta

        except yaml.YAMLError as e:
            logger.error(f"Invalid manifest YAML at {manifest_file}: {e}")
            return None
        except Exception as e:
            logger.exception(f"Error discovering plugin at {path}: {e}")
            return None

    def load(self, plugin_id: str, app: Any = None) -> Plugin | None:
        """
        Load a discovered plugin.

        Args:
            plugin_id: Plugin identifier
            app: Focomy application instance

        Returns:
            Loaded Plugin instance, or None on failure
        """
        if plugin_id in self._loaded:
            return self._loaded[plugin_id]

        meta = self._discovered.get(plugin_id)
        if not meta:
            logger.error(f"Plugin not discovered: {plugin_id}")
            return None

        if not meta.path:
            logger.error(f"Plugin path not set: {plugin_id}")
            return None

        try:
            # Check for plugin.py
            plugin_file = meta.path / "plugin.py"
            if not plugin_file.exists():
                # Try __init__.py
                plugin_file = meta.path / "__init__.py"
                if not plugin_file.exists():
                    logger.error(f"No plugin.py or __init__.py in {meta.path}")
                    meta.state = PluginState.ERROR
                    meta.error_message = "No plugin module found"
                    return None

            # Load the module
            plugin_class = self._load_plugin_class(plugin_id, plugin_file)
            if not plugin_class:
                meta.state = PluginState.ERROR
                meta.error_message = "Failed to load plugin class"
                return None

            # Instantiate plugin
            plugin = plugin_class(meta, app)

            # Update state
            meta.state = PluginState.LOADED
            self._loaded[plugin_id] = plugin

            logger.info(f"Loaded plugin: {plugin_id} v{meta.version}")
            return plugin

        except Exception as e:
            logger.exception(f"Error loading plugin {plugin_id}: {e}")
            meta.state = PluginState.ERROR
            meta.error_message = str(e)
            return None

    def _load_plugin_class(
        self,
        plugin_id: str,
        plugin_file: Path,
    ) -> type[Plugin] | None:
        """
        Load the plugin class from a file.

        Args:
            plugin_id: Plugin identifier
            plugin_file: Path to plugin module

        Returns:
            Plugin class, or None on failure
        """
        try:
            # Create module spec
            module_name = f"focomy_plugins.{plugin_id.replace('-', '_')}"
            spec = importlib.util.spec_from_file_location(
                module_name,
                plugin_file,
            )

            if not spec or not spec.loader:
                return None

            # Load module
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Find Plugin subclass
            for name in dir(module):
                obj = getattr(module, name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, Plugin)
                    and obj is not Plugin
                    and not name.startswith("_")
                ):
                    return obj

            # Check for explicit plugin_class attribute
            if hasattr(module, "plugin_class"):
                return module.plugin_class

            # Check for default class name
            class_name = (
                "".join(word.capitalize() for word in plugin_id.replace("-", "_").split("_"))
                + "Plugin"
            )

            if hasattr(module, class_name):
                return getattr(module, class_name)

            logger.error(f"No Plugin subclass found in {plugin_file}")
            return None

        except Exception as e:
            logger.exception(f"Error loading plugin module: {e}")
            return None

    def unload(self, plugin_id: str) -> bool:
        """
        Unload a loaded plugin.

        Args:
            plugin_id: Plugin identifier

        Returns:
            True if unloaded successfully
        """
        if plugin_id not in self._loaded:
            return False

        self._loaded[plugin_id]

        try:
            # Remove from loaded
            del self._loaded[plugin_id]

            # Remove module from sys.modules
            module_name = f"focomy_plugins.{plugin_id.replace('-', '_')}"
            if module_name in sys.modules:
                del sys.modules[module_name]

            # Update state
            meta = self._discovered.get(plugin_id)
            if meta:
                meta.state = PluginState.DISCOVERED

            logger.info(f"Unloaded plugin: {plugin_id}")
            return True

        except Exception as e:
            logger.exception(f"Error unloading plugin {plugin_id}: {e}")
            return False

    def reload(self, plugin_id: str, app: Any = None) -> Plugin | None:
        """
        Reload a plugin (unload and load again).

        Args:
            plugin_id: Plugin identifier
            app: Focomy application instance

        Returns:
            Reloaded Plugin instance, or None on failure
        """
        self.unload(plugin_id)
        return self.load(plugin_id, app)

    def get_loaded(self, plugin_id: str) -> Plugin | None:
        """Get a loaded plugin by ID."""
        return self._loaded.get(plugin_id)

    def get_all_loaded(self) -> dict[str, Plugin]:
        """Get all loaded plugins."""
        return self._loaded.copy()

    def get_all_discovered(self) -> dict[str, PluginMeta]:
        """Get all discovered plugins."""
        return self._discovered.copy()

    def is_loaded(self, plugin_id: str) -> bool:
        """Check if a plugin is loaded."""
        return plugin_id in self._loaded

    def check_dependencies(self, plugin_id: str) -> tuple[bool, list[str]]:
        """
        Check if plugin dependencies are satisfied.

        Args:
            plugin_id: Plugin identifier

        Returns:
            Tuple of (satisfied, missing_dependencies)
        """
        meta = self._discovered.get(plugin_id)
        if not meta:
            return False, [f"Plugin not found: {plugin_id}"]

        missing = []

        for dep in meta.dependencies:
            # Parse dependency spec (e.g., "other-plugin>=1.0.0")
            dep_id = dep.split(">=")[0].split("<=")[0].split("==")[0].strip()

            if dep_id not in self._discovered:
                missing.append(dep)
            else:
                dep_meta = self._discovered[dep_id]
                # TODO: Version comparison
                if dep_meta.state == PluginState.ERROR:
                    missing.append(f"{dep} (error state)")

        return len(missing) == 0, missing

    def check_conflicts(self, plugin_id: str) -> tuple[bool, list[str]]:
        """
        Check if plugin has conflicts with loaded plugins.

        Args:
            plugin_id: Plugin identifier

        Returns:
            Tuple of (no_conflicts, conflicting_plugins)
        """
        meta = self._discovered.get(plugin_id)
        if not meta:
            return False, [f"Plugin not found: {plugin_id}"]

        conflicts = []

        for conflict_id in meta.conflicts:
            if conflict_id in self._loaded:
                conflicts.append(conflict_id)

        # Also check if other plugins conflict with this one
        for other_id, other_meta in self._discovered.items():
            if other_id in self._loaded and plugin_id in other_meta.conflicts:
                conflicts.append(other_id)

        return len(conflicts) == 0, conflicts
