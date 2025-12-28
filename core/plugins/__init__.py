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
from .manager import PluginManager
from .hooks import HookRegistry, hook, filter_hook, action_hook
from .loader import PluginLoader

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
