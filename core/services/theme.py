"""ThemeService - theme management and rendering."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..config import settings
from .assets import get_asset_url, get_static_url, get_upload_url
from .theme_blocks import ThemeBlocksMixin
from .theme_css import ThemeCSSMixin
from .theme_defaults import create_default_theme


class ThemeConfig:
    """Theme configuration."""

    # Default values for CSS variables (used when theme.yaml is incomplete)
    DEFAULT_COLORS = {
        "primary": "#2563eb",
        "primary-hover": "#1d4ed8",
        "background": "#ffffff",
        "surface": "#f8fafc",
        "text": "#1e293b",
        "text-muted": "#64748b",
        "border": "#e2e8f0",
        "success": "#22c55e",
        "error": "#ef4444",
        "warning": "#f59e0b",
    }
    DEFAULT_FONTS = {
        "sans": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        "serif": "Georgia, 'Times New Roman', serif",
        "mono": "ui-monospace, SFMono-Regular, Menlo, monospace",
    }
    DEFAULT_SPACING = {
        "xs": "0.25rem",
        "sm": "0.5rem",
        "md": "1rem",
        "lg": "1.5rem",
        "xl": "2rem",
        "2xl": "3rem",
    }

    def __init__(self, data: dict):
        self.name = data.get("name", "default")
        self.label = data.get("label", "Default Theme")
        self.version = data.get("version", "1.0.0")
        self.author = data.get("author", "")
        self.description = data.get("description", "")
        self.preview = data.get("preview", "")

        # CSS variables (fallback to defaults if empty/missing)
        self.colors = data.get("colors") or self.DEFAULT_COLORS
        self.fonts = data.get("fonts") or self.DEFAULT_FONTS
        self.spacing = data.get("spacing") or self.DEFAULT_SPACING

        # Customization config
        self.config = data.get("config", {})

        # Widget areas and menu locations
        self.widget_areas = data.get("widget_areas", [])
        self.menu_locations = data.get("menu_locations", [])

        # Templates
        self.templates = data.get("templates", {})

        # Custom CSS
        self.custom_css = data.get("custom_css", "")


class ThemeService(ThemeBlocksMixin, ThemeCSSMixin):
    """
    Theme management service.

    Features:
    - CSS variables from YAML config
    - Jinja2 template rendering
    - Template inheritance
    - Custom CSS injection

    Block rendering provided by ThemeBlocksMixin.
    CSS generation provided by ThemeCSSMixin.
    """

    def __init__(self):
        self.themes_dir = settings.base_dir / "themes"
        self.themes_dir.mkdir(exist_ok=True)
        self._themes: dict[str, ThemeConfig] = {}
        self._current_theme: str = "default"
        self._env: Environment | None = None

    def _load_themes(self):
        """Load all theme configurations."""
        if self._themes:
            return

        for theme_dir in self.themes_dir.iterdir():
            if theme_dir.is_dir():
                config_path = theme_dir / "theme.yaml"
                if config_path.exists():
                    try:
                        with open(config_path, encoding="utf-8") as f:
                            data = yaml.safe_load(f)
                            if data:
                                theme = ThemeConfig(data)
                                self._themes[theme.name] = theme
                    except Exception as e:
                        print(f"Error loading theme {theme_dir}: {e}")

        # Ensure default theme exists
        if "default" not in self._themes:
            self._create_default_theme()

    def _create_default_theme(self):
        """Create default theme if not exists."""
        self._themes["default"] = create_default_theme(self.themes_dir, ThemeConfig)

    def get_theme(self, name: str = None) -> ThemeConfig | None:
        """Get theme configuration."""
        self._load_themes()
        name = name or self._current_theme
        return self._themes.get(name)

    def get_all_themes(self) -> dict[str, ThemeConfig]:
        """Get all themes."""
        self._load_themes()
        return self._themes.copy()

    def set_current_theme(self, name: str):
        """Set current theme."""
        self._load_themes()
        if name in self._themes:
            self._current_theme = name
            self._env = None  # Reset environment

    def get_template_env(self, theme_name: str = None) -> Environment:
        """Get Jinja2 environment for theme."""
        theme = self.get_theme(theme_name)
        active_theme = theme.name if theme else "default"

        # Use theme inheritance for template fallback
        from .theme_inheritance import ThemeInheritanceService

        inheritance_svc = ThemeInheritanceService(self.themes_dir)
        template_paths = inheritance_svc.get_template_paths(active_theme)

        # Package default theme takes priority (for pip upgrade compatibility)
        package_default = Path(__file__).parent.parent.parent / "themes" / "default" / "templates"
        if package_default.exists():
            # Remove site-local default if exists, package default takes priority
            site_default = self.themes_dir / "default" / "templates"
            template_paths = [p for p in template_paths if p != site_default]
            template_paths.insert(0, package_default)

        # Fallback if no paths found
        if not template_paths:
            template_paths = [package_default]

        env = Environment(
            loader=FileSystemLoader([str(p) for p in template_paths]),
            autoescape=select_autoescape(["html", "xml"]),
        )

        # Add custom filters
        env.filters["render_blocks"] = self._render_blocks
        env.filters["excerpt"] = self._excerpt
        env.filters["asset_url"] = get_asset_url
        env.filters["upload_url"] = get_upload_url
        env.filters["static_url"] = get_static_url
        env.filters["date"] = self._date_filter

        # Add global functions
        env.globals["asset_url"] = get_asset_url
        env.globals["upload_url"] = get_upload_url
        env.globals["static_url"] = get_static_url
        env.globals["now"] = datetime.now

        return env

    def render(
        self,
        template_name: str,
        context: dict[str, Any],
        theme_name: str = None,
    ) -> str:
        """Render a template with context."""
        env = self.get_template_env(theme_name)
        template = env.get_template(template_name)

        # Add theme CSS to context
        context["theme_css"] = self.get_css_variables(theme_name)
        context["customizations"] = self.get_customizations(theme_name)
        context["current_year"] = datetime.now().year
        context.setdefault("site_name", "Focomy")

        return template.render(**context)

    # === Customization Methods ===

    def get_customizations(self, theme_name: str = None) -> dict:
        """Get saved customizations for a theme.

        Args:
            theme_name: Theme name (uses current theme if not provided)

        Returns:
            Dict of customization values
        """
        theme = self.get_theme(theme_name)
        if not theme:
            return {}

        customizations_file = self.themes_dir / theme.name / "customizations.json"
        if customizations_file.exists():
            try:
                return json.loads(customizations_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def set_customizations(self, values: dict, theme_name: str = None) -> bool:
        """Save customizations for a theme.

        Args:
            values: Dict of customization values
            theme_name: Theme name (uses current theme if not provided)

        Returns:
            True if saved successfully
        """
        theme = self.get_theme(theme_name)
        if not theme:
            return False

        customizations_file = self.themes_dir / theme.name / "customizations.json"
        try:
            customizations_file.write_text(
                json.dumps(values, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            return True
        except Exception:
            return False

    def get_customizable_settings(self, theme_name: str = None) -> list[dict]:
        """Get list of customizable settings for a theme.

        Args:
            theme_name: Theme name (uses current theme if not provided)

        Returns:
            List of setting definitions with current values
        """
        theme = self.get_theme(theme_name)
        if not theme:
            return []

        customizations = self.get_customizations(theme_name)
        result = []

        # Site Identity (logo, favicon)
        result.append({
            "id": "site_logo",
            "type": "image",
            "label": "サイトロゴ",
            "category": "site_identity",
            "default": "",
            "value": customizations.get("site_logo", ""),
            "description": "ヘッダーに表示されるロゴ画像（推奨: 高さ60px以下）",
        })
        result.append({
            "id": "site_icon",
            "type": "image",
            "label": "サイトアイコン",
            "category": "site_identity",
            "default": "",
            "value": customizations.get("site_icon", ""),
            "description": "ファビコン・アプリアイコン（推奨: 512x512px）",
        })

        # Header Images
        result.append({
            "id": "header_image",
            "type": "image",
            "label": "ヘッダー画像",
            "category": "header",
            "default": "",
            "value": customizations.get("header_image", ""),
            "description": "ヘッダー背景画像（推奨: 1920x400px）",
        })
        result.append({
            "id": "background_image",
            "type": "image",
            "label": "背景画像",
            "category": "header",
            "default": "",
            "value": customizations.get("background_image", ""),
            "description": "サイト全体の背景画像",
        })

        # Colors
        for name, default_value in theme.colors.items():
            result.append({
                "id": f"color_{name}",
                "type": "color",
                "label": name.replace("-", " ").replace("_", " ").title(),
                "category": "colors",
                "default": default_value,
                "value": customizations.get(f"color_{name}", default_value),
            })

        # Fonts
        for name, default_value in theme.fonts.items():
            result.append({
                "id": f"font_{name}",
                "type": "font",
                "label": name.replace("-", " ").replace("_", " ").title(),
                "category": "fonts",
                "default": default_value,
                "value": customizations.get(f"font_{name}", default_value),
            })

        # Spacing
        for name, default_value in theme.spacing.items():
            result.append({
                "id": f"space_{name}",
                "type": "spacing",
                "label": name.replace("-", " ").replace("_", " ").title(),
                "category": "spacing",
                "default": default_value,
                "value": customizations.get(f"space_{name}", default_value),
            })

        # Custom CSS
        result.append({
            "id": "custom_css",
            "type": "code",
            "label": "カスタムCSS",
            "category": "custom_css",
            "default": theme.custom_css or "",
            "value": customizations.get("custom_css", theme.custom_css or ""),
            "description": "独自のCSSを追加できます",
        })

        return result


# Singleton
theme_service = ThemeService()
