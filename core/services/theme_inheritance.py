"""Theme Inheritance - Child theme support.

Allows themes to extend parent themes with selective overrides.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ThemeConfig:
    """Theme configuration."""

    name: str
    label: str
    version: str
    parent: str | None = None
    description: str = ""
    author: str = ""
    templates: dict = field(default_factory=dict)
    styles: list = field(default_factory=list)
    scripts: list = field(default_factory=list)
    settings: dict = field(default_factory=dict)


@dataclass
class ResolvedTheme:
    """Fully resolved theme with inheritance applied."""

    name: str
    inheritance_chain: list[str]
    templates: dict[str, Path]  # template_name -> file_path
    styles: list[str]  # CSS file paths
    scripts: list[str]  # JS file paths
    settings: dict[str, Any]  # Merged settings


class ThemeInheritanceService:
    """
    Service for theme inheritance and child themes.

    Usage:
        service = ThemeInheritanceService(themes_dir)

        # Get resolved theme
        theme = service.resolve_theme("my-child-theme")

        # Get template path (with fallback to parent)
        path = service.get_template_path("my-child-theme", "post.html")

        # Get all styles (parent + child)
        styles = service.get_styles("my-child-theme")
    """

    def __init__(self, themes_dir: Path):
        self.themes_dir = Path(themes_dir)
        self._cache: dict[str, ThemeConfig] = {}

    def load_theme_config(self, theme_name: str) -> ThemeConfig | None:
        """Load theme configuration from theme.yaml."""
        if theme_name in self._cache:
            return self._cache[theme_name]

        theme_dir = self.themes_dir / theme_name
        config_path = theme_dir / "theme.yaml"

        if not config_path.exists():
            return None

        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        config = ThemeConfig(
            name=theme_name,
            label=data.get("label", theme_name),
            version=data.get("version", "1.0.0"),
            parent=data.get("parent"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            templates=data.get("templates", {}),
            styles=data.get("styles", []),
            scripts=data.get("scripts", []),
            settings=data.get("settings", {}),
        )

        self._cache[theme_name] = config
        return config

    def get_inheritance_chain(self, theme_name: str) -> list[str]:
        """
        Get the inheritance chain for a theme.

        Returns list from child to ultimate parent.
        """
        chain = []
        current = theme_name
        seen = set()

        while current:
            if current in seen:
                raise ValueError(f"Circular theme inheritance detected: {current}")

            seen.add(current)
            chain.append(current)

            config = self.load_theme_config(current)
            if config and config.parent:
                current = config.parent
            else:
                break

        return chain

    def resolve_theme(self, theme_name: str) -> ResolvedTheme:
        """
        Resolve a theme with all inheritance applied.

        Child theme values override parent values.
        """
        chain = self.get_inheritance_chain(theme_name)

        # Start with empty
        templates = {}
        styles = []
        scripts = []
        settings = {}

        # Apply from parent to child (reverse order)
        for name in reversed(chain):
            config = self.load_theme_config(name)
            if not config:
                continue

            theme_dir = self.themes_dir / name

            # Merge templates (child overrides parent)
            theme_templates_dir = theme_dir / "templates"
            if theme_templates_dir.exists():
                for template_file in theme_templates_dir.rglob("*.html"):
                    rel_path = template_file.relative_to(theme_templates_dir)
                    template_name = str(rel_path)
                    templates[template_name] = template_file

            # Merge styles (parent first, then child)
            for style in config.styles:
                style_path = f"/themes/{name}/static/{style}"
                if style_path not in styles:
                    styles.append(style_path)

            # Merge scripts (parent first, then child)
            for script in config.scripts:
                script_path = f"/themes/{name}/static/{script}"
                if script_path not in scripts:
                    scripts.append(script_path)

            # Merge settings (child overrides parent)
            settings = self._deep_merge(settings, config.settings)

        return ResolvedTheme(
            name=theme_name,
            inheritance_chain=chain,
            templates=templates,
            styles=styles,
            scripts=scripts,
            settings=settings,
        )

    def get_template_path(
        self,
        theme_name: str,
        template_name: str,
    ) -> Path | None:
        """
        Get the path to a template, checking child first then parents.

        Args:
            theme_name: Theme to look in
            template_name: Template file name (e.g., "post.html")

        Returns:
            Path to template file, or None if not found
        """
        chain = self.get_inheritance_chain(theme_name)

        for name in chain:
            template_path = self.themes_dir / name / "templates" / template_name
            if template_path.exists():
                return template_path

        return None

    def get_template_paths(self, theme_name: str) -> list[Path]:
        """
        Get all template directories in inheritance order.

        For Jinja2 FileSystemLoader.
        """
        chain = self.get_inheritance_chain(theme_name)
        paths = []

        for name in chain:
            template_dir = self.themes_dir / name / "templates"
            if template_dir.exists():
                paths.append(template_dir)

        return paths

    def get_styles(self, theme_name: str) -> list[str]:
        """Get all CSS files in inheritance order (parent first)."""
        resolved = self.resolve_theme(theme_name)
        return resolved.styles

    def get_scripts(self, theme_name: str) -> list[str]:
        """Get all JS files in inheritance order (parent first)."""
        resolved = self.resolve_theme(theme_name)
        return resolved.scripts

    def get_setting(
        self,
        theme_name: str,
        key: str,
        default: Any = None,
    ) -> Any:
        """Get a theme setting with inheritance."""
        resolved = self.resolve_theme(theme_name)
        return self._get_nested(resolved.settings, key, default)

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Deep merge two dictionaries."""
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    def _get_nested(self, data: dict, key: str, default: Any = None) -> Any:
        """Get a nested value using dot notation."""
        keys = key.split(".")
        value = data

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def list_themes(self) -> list[ThemeConfig]:
        """List all available themes."""
        themes = []

        if not self.themes_dir.exists():
            return themes

        for theme_dir in self.themes_dir.iterdir():
            if theme_dir.is_dir():
                config = self.load_theme_config(theme_dir.name)
                if config:
                    themes.append(config)

        return themes

    def validate_theme(self, theme_name: str) -> list[str]:
        """Validate a theme configuration."""
        errors = []

        config = self.load_theme_config(theme_name)
        if not config:
            errors.append(f"Theme '{theme_name}' not found")
            return errors

        # Check parent exists
        if config.parent:
            parent_config = self.load_theme_config(config.parent)
            if not parent_config:
                errors.append(f"Parent theme '{config.parent}' not found")

        # Check for circular inheritance
        try:
            self.get_inheritance_chain(theme_name)
        except ValueError as e:
            errors.append(str(e))

        # Check required templates exist in chain
        required_templates = ["base.html"]
        for template in required_templates:
            path = self.get_template_path(theme_name, template)
            if not path:
                errors.append(f"Required template '{template}' not found in inheritance chain")

        return errors

    def clear_cache(self):
        """Clear the theme config cache."""
        self._cache.clear()


def get_theme_inheritance_service(themes_dir: str = "themes") -> ThemeInheritanceService:
    return ThemeInheritanceService(Path(themes_dir))
