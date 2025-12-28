"""Focomy Plugin System.

A flexible plugin architecture for extending Focomy CMS functionality.

Features:
- Hook-based extension points
- Plugin lifecycle management
- Dependency resolution
- Sandboxed execution
- Admin UI integration
- Hot reload support
"""

from .base import Plugin, PluginMeta, PluginState
from .hooks import HookRegistry, action_hook, filter_hook, hook
from .loader import PluginLoader
from .manager import PluginManager

__all__ = [
    "Plugin",
    "PluginMeta",
    "PluginState",
    "PluginManager",
    "PluginLoader",
    "HookRegistry",
    "hook",
    "filter_hook",
    "action_hook",
]
