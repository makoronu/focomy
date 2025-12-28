"""Plugin Dependency Resolver - Resolves plugin dependencies and load order.

Handles:
- Dependency resolution
- Circular dependency detection
- Load order calculation
"""

from collections import defaultdict
from dataclasses import dataclass


@dataclass
class PluginInfo:
    """Plugin metadata."""

    name: str
    version: str
    requires: list[str]  # List of required plugins
    conflicts: list[str]  # List of conflicting plugins
    provides: list[str]  # Capabilities provided


@dataclass
class DependencyError:
    """Dependency resolution error."""

    plugin: str
    error_type: str  # "missing", "circular", "conflict", "version"
    message: str
    related_plugins: list[str]


@dataclass
class ResolveResult:
    """Result of dependency resolution."""

    success: bool
    load_order: list[str]
    errors: list[DependencyError]
    warnings: list[str]


class PluginResolver:
    """
    Resolves plugin dependencies and determines load order.

    Usage:
        resolver = PluginResolver()

        # Register plugins
        resolver.register(PluginInfo(
            name="my-plugin",
            version="1.0.0",
            requires=["base-plugin"],
            conflicts=[],
            provides=["feature-x"],
        ))

        # Resolve dependencies
        result = resolver.resolve()

        if result.success:
            for plugin_name in result.load_order:
                load_plugin(plugin_name)
    """

    def __init__(self):
        self._plugins: dict[str, PluginInfo] = {}
        self._enabled: set[str] = set()

    def register(self, plugin: PluginInfo) -> None:
        """Register a plugin."""
        self._plugins[plugin.name] = plugin

    def enable(self, plugin_name: str) -> None:
        """Mark a plugin as enabled."""
        self._enabled.add(plugin_name)

    def disable(self, plugin_name: str) -> None:
        """Mark a plugin as disabled."""
        self._enabled.discard(plugin_name)

    def resolve(
        self,
        plugins_to_enable: list[str] = None,
    ) -> ResolveResult:
        """
        Resolve dependencies and calculate load order.

        Args:
            plugins_to_enable: Specific plugins to enable (uses all enabled if None)

        Returns:
            ResolveResult with load order or errors
        """
        errors = []
        warnings = []

        # Get plugins to resolve
        to_resolve = set(plugins_to_enable) if plugins_to_enable else self._enabled

        # Check for missing plugins
        for plugin_name in to_resolve:
            if plugin_name not in self._plugins:
                errors.append(
                    DependencyError(
                        plugin=plugin_name,
                        error_type="missing",
                        message=f"Plugin '{plugin_name}' not found",
                        related_plugins=[],
                    )
                )

        if errors:
            return ResolveResult(
                success=False,
                load_order=[],
                errors=errors,
                warnings=warnings,
            )

        # Collect all required plugins
        all_required = self._collect_all_dependencies(to_resolve)

        # Check for missing dependencies
        for plugin_name in all_required:
            if plugin_name not in self._plugins:
                # Find which plugins require it
                requiring = [
                    p
                    for p in to_resolve
                    if plugin_name in self._plugins.get(p, PluginInfo("", "", [], [], [])).requires
                ]
                errors.append(
                    DependencyError(
                        plugin=plugin_name,
                        error_type="missing",
                        message=f"Required plugin '{plugin_name}' not found",
                        related_plugins=requiring,
                    )
                )

        # Check for circular dependencies
        circular = self._detect_circular_dependencies(all_required)
        if circular:
            errors.append(
                DependencyError(
                    plugin=circular[0],
                    error_type="circular",
                    message=f"Circular dependency detected: {' -> '.join(circular)}",
                    related_plugins=circular,
                )
            )

        # Check for conflicts
        for plugin_name in all_required:
            plugin = self._plugins.get(plugin_name)
            if plugin:
                for conflict in plugin.conflicts:
                    if conflict in all_required:
                        errors.append(
                            DependencyError(
                                plugin=plugin_name,
                                error_type="conflict",
                                message=f"Plugin '{plugin_name}' conflicts with '{conflict}'",
                                related_plugins=[conflict],
                            )
                        )

        if errors:
            return ResolveResult(
                success=False,
                load_order=[],
                errors=errors,
                warnings=warnings,
            )

        # Calculate load order (topological sort)
        load_order = self._topological_sort(all_required)

        return ResolveResult(
            success=True,
            load_order=load_order,
            errors=[],
            warnings=warnings,
        )

    def _collect_all_dependencies(self, plugins: set[str]) -> set[str]:
        """Recursively collect all required plugins."""
        all_deps = set(plugins)
        queue = list(plugins)

        while queue:
            plugin_name = queue.pop(0)
            plugin = self._plugins.get(plugin_name)
            if plugin:
                for dep in plugin.requires:
                    if dep not in all_deps:
                        all_deps.add(dep)
                        queue.append(dep)

        return all_deps

    def _detect_circular_dependencies(self, plugins: set[str]) -> list[str]:
        """Detect circular dependencies using DFS."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = dict.fromkeys(plugins, WHITE)
        path = []

        def dfs(plugin_name: str) -> list[str] | None:
            if plugin_name not in self._plugins:
                return None

            color[plugin_name] = GRAY
            path.append(plugin_name)

            plugin = self._plugins[plugin_name]
            for dep in plugin.requires:
                if dep in color:
                    if color[dep] == GRAY:
                        # Found cycle
                        cycle_start = path.index(dep)
                        return path[cycle_start:] + [dep]
                    elif color[dep] == WHITE:
                        result = dfs(dep)
                        if result:
                            return result

            color[plugin_name] = BLACK
            path.pop()
            return None

        for plugin_name in plugins:
            if color.get(plugin_name, WHITE) == WHITE:
                result = dfs(plugin_name)
                if result:
                    return result

        return []

    def _topological_sort(self, plugins: set[str]) -> list[str]:
        """Perform topological sort for load order."""
        in_degree = dict.fromkeys(plugins, 0)
        graph = defaultdict(list)

        # Build graph
        for plugin_name in plugins:
            plugin = self._plugins.get(plugin_name)
            if plugin:
                for dep in plugin.requires:
                    if dep in plugins:
                        graph[dep].append(plugin_name)
                        in_degree[plugin_name] += 1

        # Kahn's algorithm
        queue = [p for p in plugins if in_degree[p] == 0]
        result = []

        while queue:
            # Sort queue for deterministic order
            queue.sort()
            plugin_name = queue.pop(0)
            result.append(plugin_name)

            for dependent in graph[plugin_name]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        return result

    def get_dependents(self, plugin_name: str) -> list[str]:
        """Get plugins that depend on the given plugin."""
        dependents = []
        for name, plugin in self._plugins.items():
            if plugin_name in plugin.requires:
                dependents.append(name)
        return dependents

    def get_dependencies(self, plugin_name: str) -> list[str]:
        """Get plugins that the given plugin depends on."""
        plugin = self._plugins.get(plugin_name)
        if plugin:
            return list(plugin.requires)
        return []

    def can_disable(self, plugin_name: str) -> tuple[bool, list[str]]:
        """Check if a plugin can be safely disabled."""
        dependents = []
        for name in self._enabled:
            if name != plugin_name:
                plugin = self._plugins.get(name)
                if plugin and plugin_name in plugin.requires:
                    dependents.append(name)

        return len(dependents) == 0, dependents

    def get_plugin_info(self, plugin_name: str) -> PluginInfo | None:
        """Get plugin information."""
        return self._plugins.get(plugin_name)

    def list_plugins(self) -> list[PluginInfo]:
        """List all registered plugins."""
        return list(self._plugins.values())


def get_plugin_resolver() -> PluginResolver:
    return PluginResolver()
