"""SettingsService - site settings management.

Hybrid approach: YAML defaults + Database overrides.
DB settings take precedence over config.yaml.
"""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings as app_settings
from .entity import EntityService

# Default settings by category
DEFAULT_SETTINGS = {
    "site": {
        "name": "My Site",
        "tagline": "",
        "url": "http://localhost:8000",
        "language": "ja",
        "timezone": "Asia/Tokyo",
    },
    "seo": {
        "title_separator": " | ",
        "default_description": "",
        "default_og_image": "",
    },
    "media": {
        "max_size": 10485760,
        "image_max_width": 1920,
        "image_max_height": 1920,
        "image_quality": 85,
        "image_format": "webp",
    },
    "security": {
        "session_expire": 86400,
        "login_attempts": 5,
        "lockout_duration": 900,
        "password_min_length": 12,
    },
    "features": {
        "media": True,
        "comment": False,
        "form": True,
        "wordpress_import": False,
        "menu": True,
        "widget": True,
    },
}


class SettingsService:
    """
    Settings management service.

    Provides a unified interface for site settings.
    DB values override YAML config values.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.entity_svc = EntityService(db)
        self._cache: dict[str, Any] = {}

    async def get(self, key: str, default: Any = None) -> Any:
        """
        Get a setting value.

        Priority: DB > config.yaml > default
        """
        # Check cache
        if key in self._cache:
            return self._cache[key]

        # Try DB
        db_value = await self._get_db_value(key)
        if db_value is not None:
            self._cache[key] = db_value
            return db_value

        # Try config.yaml
        yaml_value = self._get_yaml_value(key)
        if yaml_value is not None:
            return yaml_value

        # Return default
        return default

    async def set(self, key: str, value: Any, category: str = "site", user_id: str = None) -> bool:
        """
        Set a setting value in the database.

        This overrides the YAML config value.
        """
        # Determine value type
        value_type = "string"
        if isinstance(value, bool):
            value_type = "boolean"
            value = "true" if value else "false"
        elif isinstance(value, (int, float)):
            value_type = "number"
            value = str(value)
        elif isinstance(value, (dict, list)):
            value_type = "json"
            value = json.dumps(value)
        else:
            value = str(value)

        # Find or create setting
        entities = await self.entity_svc.find(
            "site_setting",
            limit=1,
            filters={"key": key},
        )

        if entities:
            # Update existing
            await self.entity_svc.update(
                entities[0].id,
                {"key": key, "value": value, "value_type": value_type, "category": category},
                user_id=user_id,
                create_revision=False,
            )
        else:
            # Create new
            await self.entity_svc.create(
                "site_setting",
                {
                    "key": key,
                    "value": value,
                    "value_type": value_type,
                    "category": category,
                },
                user_id=user_id,
            )

        # Clear cache
        self._cache.pop(key, None)
        return True

    async def delete(self, key: str, user_id: str = None) -> bool:
        """Delete a setting from the database (reverts to YAML default)."""
        entities = await self.entity_svc.find(
            "site_setting",
            limit=1,
            filters={"key": key},
        )

        if entities:
            await self.entity_svc.delete(entities[0].id, user_id=user_id)
            self._cache.pop(key, None)
            return True
        return False

    async def get_all(self, category: str = None) -> dict[str, Any]:
        """Get all settings, optionally filtered by category."""
        result = {}

        # Start with defaults
        if category:
            defaults = DEFAULT_SETTINGS.get(category, {})
            for key, value in defaults.items():
                result[f"{category}.{key}"] = value
        else:
            for cat, settings in DEFAULT_SETTINGS.items():
                for key, value in settings.items():
                    result[f"{cat}.{key}"] = value

        # Override with YAML config
        yaml_settings = self._get_all_yaml_settings(category)
        result.update(yaml_settings)

        # Override with DB settings
        db_settings = await self._get_all_db_settings(category)
        result.update(db_settings)

        return result

    async def get_by_category(self, category: str) -> dict[str, Any]:
        """Get all settings for a category as a flat dict."""
        all_settings = await self.get_all(category)
        result = {}
        prefix = f"{category}."

        for key, value in all_settings.items():
            if key.startswith(prefix):
                short_key = key[len(prefix) :]
                result[short_key] = value

        return result

    async def _get_db_value(self, key: str) -> Any | None:
        """Get a setting value from the database."""
        entities = await self.entity_svc.find(
            "site_setting",
            limit=1,
            filters={"key": key},
        )

        if not entities:
            return None

        data = self.entity_svc.serialize(entities[0])
        raw_value = data.get("value", "")
        value_type = data.get("value_type", "string")

        return self._parse_value(raw_value, value_type)

    async def _get_all_db_settings(self, category: str = None) -> dict[str, Any]:
        """Get all settings from the database."""
        filters = {"category": category} if category else {}
        entities = await self.entity_svc.find(
            "site_setting",
            limit=1000,
            filters=filters,
        )

        result = {}
        for e in entities:
            data = self.entity_svc.serialize(e)
            key = data.get("key", "")
            raw_value = data.get("value", "")
            value_type = data.get("value_type", "string")

            if key:
                result[key] = self._parse_value(raw_value, value_type)

        return result

    def _get_yaml_value(self, key: str) -> Any | None:
        """Get a setting value from YAML config."""
        parts = key.split(".", 1)
        if len(parts) != 2:
            return None

        category, setting = parts

        # Map to config attributes
        config_map = {
            "site": app_settings.site,
            "seo": app_settings.seo,
            "media": app_settings.media,
            "security": app_settings.security,
            "theme": app_settings.theme,
            "features": app_settings.features,
        }

        config_obj = config_map.get(category)
        if not config_obj:
            return None

        return getattr(config_obj, setting, None)

    def _get_all_yaml_settings(self, category: str = None) -> dict[str, Any]:
        """Get all settings from YAML config."""
        result = {}

        config_map = {
            "site": app_settings.site,
            "seo": app_settings.seo,
            "media": app_settings.media,
            "security": app_settings.security,
            "theme": app_settings.theme,
            "features": app_settings.features,
        }

        categories = [category] if category else config_map.keys()

        for cat in categories:
            config_obj = config_map.get(cat)
            if config_obj:
                for field in config_obj.__fields__.keys():
                    value = getattr(config_obj, field, None)
                    if value is not None:
                        result[f"{cat}.{field}"] = value

        return result

    def _parse_value(self, raw_value: str, value_type: str) -> Any:
        """Parse a raw string value to its proper type."""
        if value_type == "boolean":
            return raw_value.lower() in ("true", "1", "yes")
        elif value_type == "number":
            try:
                if "." in raw_value:
                    return float(raw_value)
                return int(raw_value)
            except ValueError:
                return raw_value
        elif value_type == "json":
            try:
                return json.loads(raw_value)
            except json.JSONDecodeError:
                return raw_value
        return raw_value
