"""Configuration Priority Service - Manages config sources and priorities.

Defines clear priority order:
1. Environment variables (highest)
2. Database settings
3. YAML config files
4. Defaults (lowest)
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigSource:
    """Configuration sources by priority (higher = more important) - integer constants."""

    DEFAULT = 0
    YAML = 10
    DATABASE = 20
    ENVIRONMENT = 30

    ALL = [DEFAULT, YAML, DATABASE, ENVIRONMENT]


@dataclass
class ConfigValue:
    """A configuration value with source information."""

    key: str
    value: Any
    source: int  # Use ConfigSource constants
    source_detail: str  # e.g., "ENV:DATABASE_URL" or "config.yaml"


@dataclass
class ConfigConflict:
    """Represents a configuration conflict."""

    key: str
    values: list[ConfigValue]
    resolved_value: Any
    resolved_source: int  # Use ConfigSource constants


class ConfigPriorityService:
    """
    Service for managing configuration with clear priorities.

    Priority order (highest to lowest):
    1. Environment variables
    2. Database settings
    3. YAML config files
    4. Defaults

    Usage:
        config = ConfigPriorityService()

        # Load sources
        config.load_yaml("config.yaml")
        config.load_defaults({"site_name": "My Site"})

        # Get value (automatically resolves priority)
        name = config.get("site_name")

        # Get with source info
        value = config.get_with_source("site_name")
        print(f"{value.key} = {value.value} (from {value.source.name})")

        # Detect conflicts
        conflicts = config.detect_conflicts()
    """

    # Environment variable prefix
    ENV_PREFIX = "FOCOMY_"

    # Keys that can be set from environment
    ENV_ALLOWED_KEYS = {
        "DATABASE_URL",
        "SECRET_KEY",
        "DEBUG",
        "SITE_URL",
        "ADMIN_EMAIL",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "S3_BUCKET",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "REDIS_URL",
        "SENTRY_DSN",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
    }

    def __init__(self):
        self._defaults: dict[str, Any] = {}
        self._yaml_values: dict[str, Any] = {}
        self._db_values: dict[str, Any] = {}
        self._yaml_file: str = ""

    def load_defaults(self, defaults: dict[str, Any]) -> None:
        """Load default values."""
        self._defaults = defaults.copy()

    def load_yaml(self, yaml_path: str) -> None:
        """Load values from YAML config file."""
        path = Path(yaml_path)
        if not path.exists():
            return

        self._yaml_file = yaml_path

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        self._yaml_values = self._flatten_dict(data)

    def load_database_settings(self, settings: dict[str, Any]) -> None:
        """Load values from database settings."""
        self._db_values = settings.copy()

    def _flatten_dict(
        self,
        data: dict,
        prefix: str = "",
    ) -> dict[str, Any]:
        """Flatten nested dict to dot-notation keys."""
        result = {}

        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key

            if isinstance(value, dict):
                result.update(self._flatten_dict(value, full_key))
            else:
                result[full_key] = value

        return result

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value (respects priority)."""
        value_info = self.get_with_source(key)
        if value_info:
            return value_info.value
        return default

    def get_with_source(self, key: str) -> ConfigValue | None:
        """Get a configuration value with source information."""
        # Check environment first (highest priority)
        env_value = self._get_from_env(key)
        if env_value is not None:
            return ConfigValue(
                key=key,
                value=env_value,
                source=ConfigSource.ENVIRONMENT,
                source_detail=f"ENV:{self.ENV_PREFIX}{key.upper()}",
            )

        # Check database settings
        if key in self._db_values:
            return ConfigValue(
                key=key,
                value=self._db_values[key],
                source=ConfigSource.DATABASE,
                source_detail="Database",
            )

        # Check YAML config
        if key in self._yaml_values:
            return ConfigValue(
                key=key,
                value=self._yaml_values[key],
                source=ConfigSource.YAML,
                source_detail=self._yaml_file,
            )

        # Check defaults
        if key in self._defaults:
            return ConfigValue(
                key=key,
                value=self._defaults[key],
                source=ConfigSource.DEFAULT,
                source_detail="Default",
            )

        return None

    def _get_from_env(self, key: str) -> Any | None:
        """Get value from environment variable."""
        # Convert dot notation to uppercase
        env_key = key.upper().replace(".", "_")

        # Check if allowed
        if env_key not in self.ENV_ALLOWED_KEYS:
            # Also check with prefix
            if not env_key.startswith(self.ENV_PREFIX.rstrip("_")):
                return None

        # Try with prefix
        full_key = f"{self.ENV_PREFIX}{env_key}"
        value = os.environ.get(full_key)

        if value is None:
            # Try without prefix for common keys
            value = os.environ.get(env_key)

        if value is not None:
            # Type conversion
            return self._parse_env_value(value)

        return None

    def _parse_env_value(self, value: str) -> Any:
        """Parse environment variable value."""
        # Boolean
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False

        # Number
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        return value

    def get_all_values(self) -> dict[str, ConfigValue]:
        """Get all configuration values with sources."""
        all_keys = set()
        all_keys.update(self._defaults.keys())
        all_keys.update(self._yaml_values.keys())
        all_keys.update(self._db_values.keys())

        result = {}
        for key in all_keys:
            value = self.get_with_source(key)
            if value:
                result[key] = value

        return result

    def detect_conflicts(self) -> list[ConfigConflict]:
        """Detect keys with values in multiple sources."""
        conflicts = []
        all_keys = set()
        all_keys.update(self._defaults.keys())
        all_keys.update(self._yaml_values.keys())
        all_keys.update(self._db_values.keys())

        for key in all_keys:
            values = []

            if key in self._defaults:
                values.append(
                    ConfigValue(
                        key=key,
                        value=self._defaults[key],
                        source=ConfigSource.DEFAULT,
                        source_detail="Default",
                    )
                )

            if key in self._yaml_values:
                values.append(
                    ConfigValue(
                        key=key,
                        value=self._yaml_values[key],
                        source=ConfigSource.YAML,
                        source_detail=self._yaml_file,
                    )
                )

            if key in self._db_values:
                values.append(
                    ConfigValue(
                        key=key,
                        value=self._db_values[key],
                        source=ConfigSource.DATABASE,
                        source_detail="Database",
                    )
                )

            env_value = self._get_from_env(key)
            if env_value is not None:
                values.append(
                    ConfigValue(
                        key=key,
                        value=env_value,
                        source=ConfigSource.ENVIRONMENT,
                        source_detail=f"ENV:{self.ENV_PREFIX}{key.upper()}",
                    )
                )

            if len(values) > 1:
                # Find unique values
                unique_values = {}
                for v in values:
                    if v.value not in unique_values.values():
                        unique_values[v.source] = v.value

                if len(unique_values) > 1:
                    resolved = self.get_with_source(key)
                    conflicts.append(
                        ConfigConflict(
                            key=key,
                            values=values,
                            resolved_value=resolved.value if resolved else None,
                            resolved_source=resolved.source if resolved else ConfigSource.DEFAULT,
                        )
                    )

        return conflicts

    def explain_resolution(self, key: str) -> str:
        """Explain how a configuration value was resolved."""
        lines = [f"Configuration resolution for '{key}':", ""]

        sources = []

        if key in self._defaults:
            sources.append(f"  DEFAULT: {self._defaults[key]}")

        if key in self._yaml_values:
            sources.append(f"  YAML ({self._yaml_file}): {self._yaml_values[key]}")

        if key in self._db_values:
            sources.append(f"  DATABASE: {self._db_values[key]}")

        env_value = self._get_from_env(key)
        if env_value is not None:
            sources.append(f"  ENVIRONMENT: {env_value}")

        if not sources:
            lines.append("  No value found in any source")
        else:
            lines.append("Sources (lowest to highest priority):")
            lines.extend(sources)
            lines.append("")

            resolved = self.get_with_source(key)
            if resolved:
                lines.append(f"Resolved value: {resolved.value} (from {resolved.source.name})")

        return "\n".join(lines)

    def set_in_database(self, key: str, value: Any) -> None:
        """Set a value in database storage."""
        self._db_values[key] = value

    def remove_from_database(self, key: str) -> None:
        """Remove a value from database storage."""
        self._db_values.pop(key, None)


def get_config_priority_service() -> ConfigPriorityService:
    return ConfigPriorityService()
