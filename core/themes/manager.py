"""Theme Manager - Local theme discovery and management."""

import json
import logging
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

from ..utils import utcnow

logger = logging.getLogger(__name__)


class ThemeState:
    """Theme lifecycle states (string constants)."""

    AVAILABLE = "available"
    ACTIVE = "active"
    INACTIVE = "inactive"
    UPDATING = "updating"
    ERROR = "error"

    ALL = [AVAILABLE, ACTIVE, INACTIVE, UPDATING, ERROR]


@dataclass
class ThemeMeta:
    """Theme metadata from theme.yaml."""

    # Required
    id: str
    name: str
    version: str

    # Optional
    description: str = ""
    author: str = ""
    author_url: str = ""
    theme_url: str = ""
    license: str = ""
    screenshot: str = ""
    tags: list[str] = field(default_factory=list)

    # Parent theme for child themes
    parent: str | None = None

    # Features
    supports: list[str] = field(default_factory=list)
    colors: dict[str, str] = field(default_factory=dict)
    fonts: dict[str, str] = field(default_factory=dict)

    # Customizer settings
    customizer_sections: list[dict] = field(default_factory=list)

    # Template locations
    templates: dict[str, str] = field(default_factory=dict)

    # Runtime info
    path: Path | None = None
    state: ThemeState = ThemeState.AVAILABLE
    error_message: str = ""
    activated_at: datetime | None = None


@dataclass
class ThemeInfo:
    """Extended theme information for admin UI."""

    meta: ThemeMeta
    is_active: bool = False
    has_parent: bool = False
    parent_exists: bool = True
    customizations: dict = field(default_factory=dict)
    template_count: int = 0
    asset_size: int = 0


class ThemeManager:
    """
    Manages local themes.

    Handles:
    - Theme discovery from filesystem
    - Theme activation/deactivation
    - Child theme resolution
    - Template lookup
    - Asset management
    """

    def __init__(
        self,
        themes_dir: Path,
        data_dir: Path,
    ):
        """
        Initialize theme manager.

        Args:
            themes_dir: Directory containing themes
            data_dir: Directory for theme data and customizations
        """
        self.themes_dir = Path(themes_dir)
        self.data_dir = Path(data_dir)

        self._themes: dict[str, ThemeMeta] = {}
        self._active_theme_id: str | None = None
        self._customizations: dict[str, dict] = {}

        # Ensure directories exist
        self.themes_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._state_file = self.data_dir / "theme_state.json"
        self._customizations_file = self.data_dir / "theme_customizations.json"

        self._load_state()

    def discover(self) -> dict[str, ThemeMeta]:
        """
        Discover all themes in themes directory.

        Returns:
            Dict of theme IDs to metadata
        """
        self._themes = {}

        if not self.themes_dir.exists():
            return {}

        for item in self.themes_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                meta = self._discover_theme(item)
                if meta:
                    self._themes[meta.id] = meta

        return self._themes

    def _discover_theme(self, path: Path) -> ThemeMeta | None:
        """
        Discover a single theme.

        Args:
            path: Path to theme directory

        Returns:
            ThemeMeta if valid theme, None otherwise
        """
        # Check for theme.yaml
        theme_file = path / "theme.yaml"
        if not theme_file.exists():
            theme_file = path / "theme.yml"
            if not theme_file.exists():
                return None

        try:
            data = yaml.safe_load(theme_file.read_text())

            if not data.get("id"):
                data["id"] = path.name

            if not data.get("name"):
                data["name"] = data["id"].replace("-", " ").title()

            if not data.get("version"):
                data["version"] = "1.0.0"

            meta = ThemeMeta(
                id=data["id"],
                name=data["name"],
                version=data["version"],
                description=data.get("description", ""),
                author=data.get("author", ""),
                author_url=data.get("author_url", ""),
                theme_url=data.get("theme_url", ""),
                license=data.get("license", ""),
                screenshot=data.get("screenshot", "screenshot.png"),
                tags=data.get("tags", []),
                parent=data.get("parent"),
                supports=data.get("supports", []),
                colors=data.get("colors", {}),
                fonts=data.get("fonts", {}),
                customizer_sections=data.get("customizer", []),
                templates=data.get("templates", {}),
                path=path,
                state=(
                    ThemeState.ACTIVE
                    if data["id"] == self._active_theme_id
                    else ThemeState.INACTIVE
                ),
            )

            return meta

        except yaml.YAMLError as e:
            logger.error(f"Invalid theme.yaml at {theme_file}: {e}")
            return None
        except Exception as e:
            logger.exception(f"Error discovering theme at {path}: {e}")
            return None

    def get_all_themes(self) -> list[ThemeInfo]:
        """
        Get information about all themes.

        Returns:
            List of ThemeInfo for all discovered themes
        """
        result = []

        for theme_id, meta in self._themes.items():
            # Check parent theme
            has_parent = meta.parent is not None
            parent_exists = True
            if has_parent and meta.parent not in self._themes:
                parent_exists = False

            # Count templates
            template_count = 0
            if meta.path:
                templates_dir = meta.path / "templates"
                if templates_dir.exists():
                    template_count = len(list(templates_dir.glob("**/*.html")))

            # Calculate asset size
            asset_size = 0
            if meta.path:
                assets_dir = meta.path / "assets"
                if assets_dir.exists():
                    for f in assets_dir.rglob("*"):
                        if f.is_file():
                            asset_size += f.stat().st_size

            info = ThemeInfo(
                meta=meta,
                is_active=theme_id == self._active_theme_id,
                has_parent=has_parent,
                parent_exists=parent_exists,
                customizations=self._customizations.get(theme_id, {}),
                template_count=template_count,
                asset_size=asset_size,
            )
            result.append(info)

        return result

    def get_theme(self, theme_id: str) -> ThemeMeta | None:
        """Get theme metadata by ID."""
        return self._themes.get(theme_id)

    def get_active_theme(self) -> ThemeMeta | None:
        """Get currently active theme."""
        if self._active_theme_id:
            return self._themes.get(self._active_theme_id)
        return None

    def activate(self, theme_id: str) -> tuple[bool, str]:
        """
        Activate a theme.

        Args:
            theme_id: Theme identifier

        Returns:
            Tuple of (success, message)
        """
        if theme_id not in self._themes:
            return False, f"Theme not found: {theme_id}"

        theme = self._themes[theme_id]

        # Check parent theme exists
        if theme.parent and theme.parent not in self._themes:
            return False, f"Parent theme not found: {theme.parent}"

        # Deactivate current theme
        if self._active_theme_id and self._active_theme_id in self._themes:
            self._themes[self._active_theme_id].state = ThemeState.INACTIVE

        # Activate new theme
        self._active_theme_id = theme_id
        theme.state = ThemeState.ACTIVE
        theme.activated_at = utcnow()

        self._save_state()

        logger.info(f"Activated theme: {theme_id}")
        return True, "Theme activated successfully"

    def get_template_path(
        self,
        template_name: str,
        theme_id: str | None = None,
    ) -> Path | None:
        """
        Find template file path, checking child theme first.

        Args:
            template_name: Template name (e.g., "post.html")
            theme_id: Optional theme ID (uses active theme if not provided)

        Returns:
            Path to template file, or None if not found
        """
        theme_id = theme_id or self._active_theme_id
        if not theme_id:
            return None

        theme = self._themes.get(theme_id)
        if not theme or not theme.path:
            return None

        # Check child theme first
        template_path = theme.path / "templates" / template_name
        if template_path.exists():
            return template_path

        # Check parent theme
        if theme.parent:
            parent = self._themes.get(theme.parent)
            if parent and parent.path:
                parent_template = parent.path / "templates" / template_name
                if parent_template.exists():
                    return parent_template

        return None

    def get_asset_path(
        self,
        asset_name: str,
        theme_id: str | None = None,
    ) -> Path | None:
        """
        Find asset file path.

        Args:
            asset_name: Asset path (e.g., "css/style.css")
            theme_id: Optional theme ID

        Returns:
            Path to asset file, or None if not found
        """
        theme_id = theme_id or self._active_theme_id
        if not theme_id:
            return None

        theme = self._themes.get(theme_id)
        if not theme or not theme.path:
            return None

        # Check child theme first
        asset_path = theme.path / "assets" / asset_name
        if asset_path.exists():
            return asset_path

        # Check parent theme
        if theme.parent:
            parent = self._themes.get(theme.parent)
            if parent and parent.path:
                parent_asset = parent.path / "assets" / asset_name
                if parent_asset.exists():
                    return parent_asset

        return None

    def get_screenshot_url(self, theme_id: str) -> str | None:
        """Get screenshot URL for a theme."""
        theme = self._themes.get(theme_id)
        if not theme:
            return None

        return f"/themes/{theme_id}/screenshot.png"

    def install_from_zip(self, zip_path: Path) -> tuple[bool, str, str | None]:
        """
        Install a theme from a ZIP file.

        Args:
            zip_path: Path to ZIP file

        Returns:
            Tuple of (success, message, theme_id)
        """
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                # Find theme.yaml in zip
                theme_yaml = None
                theme_root = ""

                for name in zf.namelist():
                    if name.endswith("theme.yaml") or name.endswith("theme.yml"):
                        theme_yaml = name
                        theme_root = str(Path(name).parent)
                        break

                if not theme_yaml:
                    return False, "No theme.yaml found in ZIP", None

                # Parse theme.yaml
                yaml_content = zf.read(theme_yaml).decode("utf-8")
                data = yaml.safe_load(yaml_content)

                theme_id = data.get("id", Path(theme_root).name if theme_root else "unknown")

                # Check if theme exists
                theme_dir = self.themes_dir / theme_id
                if theme_dir.exists():
                    # Backup existing
                    backup_dir = (
                        self.data_dir
                        / "backups"
                        / f"{theme_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    )
                    shutil.move(theme_dir, backup_dir)

                # Extract
                theme_dir.mkdir(parents=True)

                for name in zf.namelist():
                    if name.startswith(theme_root):
                        rel_path = name[len(theme_root) :].lstrip("/")
                        if rel_path:
                            target = theme_dir / rel_path
                            if name.endswith("/"):
                                target.mkdir(parents=True, exist_ok=True)
                            else:
                                target.parent.mkdir(parents=True, exist_ok=True)
                                target.write_bytes(zf.read(name))

                # Re-discover themes
                self.discover()

                logger.info(f"Installed theme: {theme_id}")
                return True, "Theme installed successfully", theme_id

        except Exception as e:
            logger.exception(f"Error installing theme from ZIP: {e}")
            return False, f"Installation error: {e}", None

    def uninstall(self, theme_id: str) -> tuple[bool, str]:
        """
        Uninstall a theme.

        Args:
            theme_id: Theme identifier

        Returns:
            Tuple of (success, message)
        """
        if theme_id == self._active_theme_id:
            return False, "Cannot uninstall active theme"

        theme = self._themes.get(theme_id)
        if not theme:
            return False, f"Theme not found: {theme_id}"

        if not theme.path or not theme.path.exists():
            return False, "Theme path not found"

        try:
            # Backup before deletion
            backup_dir = (
                self.data_dir / "backups" / f"{theme_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            )
            shutil.move(theme.path, backup_dir)

            # Remove from registry
            del self._themes[theme_id]

            # Remove customizations
            self._customizations.pop(theme_id, None)
            self._save_customizations()

            logger.info(f"Uninstalled theme: {theme_id}")
            return True, "Theme uninstalled successfully"

        except Exception as e:
            logger.exception(f"Error uninstalling theme: {e}")
            return False, f"Uninstall error: {e}"

    def export(self, theme_id: str, output_path: Path) -> tuple[bool, str]:
        """
        Export a theme to a ZIP file.

        Args:
            theme_id: Theme identifier
            output_path: Output ZIP file path

        Returns:
            Tuple of (success, message)
        """
        theme = self._themes.get(theme_id)
        if not theme or not theme.path:
            return False, f"Theme not found: {theme_id}"

        try:
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in theme.path.rglob("*"):
                    if file_path.is_file():
                        arc_name = f"{theme_id}/{file_path.relative_to(theme.path)}"
                        zf.write(file_path, arc_name)

            logger.info(f"Exported theme: {theme_id} to {output_path}")
            return True, f"Theme exported to {output_path}"

        except Exception as e:
            logger.exception(f"Error exporting theme: {e}")
            return False, f"Export error: {e}"

    def get_customizations(self, theme_id: str | None = None) -> dict:
        """Get theme customizations."""
        theme_id = theme_id or self._active_theme_id
        return self._customizations.get(theme_id, {}).copy() if theme_id else {}

    def set_customizations(self, customizations: dict, theme_id: str | None = None) -> None:
        """Set theme customizations."""
        theme_id = theme_id or self._active_theme_id
        if theme_id:
            self._customizations[theme_id] = customizations
            self._save_customizations()

    def _load_state(self) -> None:
        """Load theme state from file."""
        if self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text())
                self._active_theme_id = data.get("active_theme")
            except Exception as e:
                logger.warning(f"Failed to load theme state: {e}")

        if self._customizations_file.exists():
            try:
                self._customizations = json.loads(self._customizations_file.read_text())
            except Exception as e:
                logger.warning(f"Failed to load customizations: {e}")

    def _save_state(self) -> None:
        """Save theme state to file."""
        try:
            data = {
                "active_theme": self._active_theme_id,
                "updated_at": utcnow().isoformat(),
            }
            self._state_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.exception(f"Failed to save theme state: {e}")

    def _save_customizations(self) -> None:
        """Save customizations to file."""
        try:
            self._customizations_file.write_text(json.dumps(self._customizations, indent=2))
        except Exception as e:
            logger.exception(f"Failed to save customizations: {e}")
