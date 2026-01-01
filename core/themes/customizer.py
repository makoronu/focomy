"""Theme Customizer - Live theme customization system."""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..utils import utcnow

logger = logging.getLogger(__name__)


class SettingType:
    """Types of customizer settings (string constants)."""

    TEXT = "text"
    TEXTAREA = "textarea"
    NUMBER = "number"
    COLOR = "color"
    IMAGE = "image"
    FONT = "font"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    RANGE = "range"
    CODE = "code"
    SPACING = "spacing"
    TYPOGRAPHY = "typography"

    ALL = [TEXT, TEXTAREA, NUMBER, COLOR, IMAGE, FONT, SELECT, CHECKBOX, RADIO, RANGE, CODE, SPACING, TYPOGRAPHY]


@dataclass
class CustomizerSetting:
    """A single customizer setting."""

    id: str
    label: str
    type: str
    default: Any = None
    description: str = ""
    section: str = ""

    # Type-specific options
    choices: list[dict] = field(default_factory=list)  # For select/radio
    min: float | None = None  # For number/range
    max: float | None = None
    step: float | None = None
    unit: str = ""  # px, em, rem, %
    placeholder: str = ""

    # Validation
    required: bool = False
    pattern: str = ""

    # Dependencies
    depends_on: dict | None = None  # {"setting_id": "value"}

    # Output
    css_property: str = ""  # CSS property to generate
    css_selector: str = ""  # CSS selector to apply to
    css_template: str = ""  # Template: "{value}px" or custom


@dataclass
class CustomizerSection:
    """A section of the customizer panel."""

    id: str
    title: str
    description: str = ""
    icon: str = ""
    priority: int = 10
    settings: list[CustomizerSetting] = field(default_factory=list)


@dataclass
class CustomizerPanel:
    """A panel containing multiple sections."""

    id: str
    title: str
    description: str = ""
    priority: int = 10
    sections: list[CustomizerSection] = field(default_factory=list)


class ThemeCustomizer:
    """
    Theme customizer for live preview and CSS generation.

    Features:
    - Live preview without saving
    - CSS variable generation
    - Custom CSS support
    - Font loading
    - Responsive previews
    - Undo/redo support
    """

    # Default sections that all themes get
    DEFAULT_SECTIONS = [
        CustomizerSection(
            id="site_identity",
            title="Site Identity",
            icon="building",
            priority=1,
            settings=[
                CustomizerSetting(
                    id="site_logo",
                    label="Logo",
                    type=SettingType.IMAGE,
                    description="Upload your site logo",
                ),
                CustomizerSetting(
                    id="site_icon",
                    label="Site Icon",
                    type=SettingType.IMAGE,
                    description="Used as favicon and app icon",
                ),
            ],
        ),
        CustomizerSection(
            id="colors",
            title="Colors",
            icon="palette",
            priority=10,
            settings=[
                CustomizerSetting(
                    id="color_primary",
                    label="Primary Color",
                    type=SettingType.COLOR,
                    default="#3B82F6",
                    css_property="--color-primary",
                    css_selector=":root",
                ),
                CustomizerSetting(
                    id="color_secondary",
                    label="Secondary Color",
                    type=SettingType.COLOR,
                    default="#6B7280",
                    css_property="--color-secondary",
                    css_selector=":root",
                ),
                CustomizerSetting(
                    id="color_accent",
                    label="Accent Color",
                    type=SettingType.COLOR,
                    default="#10B981",
                    css_property="--color-accent",
                    css_selector=":root",
                ),
                CustomizerSetting(
                    id="color_background",
                    label="Background Color",
                    type=SettingType.COLOR,
                    default="#FFFFFF",
                    css_property="--color-background",
                    css_selector=":root",
                ),
                CustomizerSetting(
                    id="color_text",
                    label="Text Color",
                    type=SettingType.COLOR,
                    default="#1F2937",
                    css_property="--color-text",
                    css_selector=":root",
                ),
            ],
        ),
        CustomizerSection(
            id="typography",
            title="Typography",
            icon="type",
            priority=20,
            settings=[
                CustomizerSetting(
                    id="font_heading",
                    label="Heading Font",
                    type=SettingType.FONT,
                    default="Inter",
                    css_property="--font-heading",
                    css_selector=":root",
                ),
                CustomizerSetting(
                    id="font_body",
                    label="Body Font",
                    type=SettingType.FONT,
                    default="Inter",
                    css_property="--font-body",
                    css_selector=":root",
                ),
                CustomizerSetting(
                    id="font_size_base",
                    label="Base Font Size",
                    type=SettingType.RANGE,
                    default=16,
                    min=12,
                    max=24,
                    step=1,
                    unit="px",
                    css_property="--font-size-base",
                    css_selector=":root",
                    css_template="{value}px",
                ),
            ],
        ),
        CustomizerSection(
            id="layout",
            title="Layout",
            icon="layout",
            priority=30,
            settings=[
                CustomizerSetting(
                    id="container_width",
                    label="Container Width",
                    type=SettingType.RANGE,
                    default=1200,
                    min=800,
                    max=1600,
                    step=50,
                    unit="px",
                    css_property="--container-width",
                    css_selector=":root",
                    css_template="{value}px",
                ),
                CustomizerSetting(
                    id="sidebar_position",
                    label="Sidebar Position",
                    type=SettingType.SELECT,
                    default="right",
                    choices=[
                        {"value": "left", "label": "Left"},
                        {"value": "right", "label": "Right"},
                        {"value": "none", "label": "No Sidebar"},
                    ],
                ),
            ],
        ),
        CustomizerSection(
            id="custom_css",
            title="Custom CSS",
            icon="code",
            priority=100,
            settings=[
                CustomizerSetting(
                    id="custom_css",
                    label="Custom CSS",
                    type=SettingType.CODE,
                    default="",
                    description="Add your own CSS styles",
                ),
            ],
        ),
    ]

    # Common web fonts
    GOOGLE_FONTS = [
        "Inter",
        "Roboto",
        "Open Sans",
        "Lato",
        "Montserrat",
        "Poppins",
        "Raleway",
        "Nunito",
        "Source Sans Pro",
        "Ubuntu",
        "Playfair Display",
        "Merriweather",
        "Noto Sans JP",
        "Noto Serif JP",
    ]

    def __init__(
        self,
        theme_manager: Any,
        data_dir: Path,
    ):
        """
        Initialize customizer.

        Args:
            theme_manager: ThemeManager instance
            data_dir: Directory for storing customization data
        """
        self.theme_manager = theme_manager
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._panels: list[CustomizerPanel] = []
        self._preview_values: dict[str, Any] = {}
        self._history: list[dict] = []
        self._history_index = -1

    def get_panels(self, theme_id: str | None = None) -> list[CustomizerPanel]:
        """
        Get all customizer panels for a theme.

        Args:
            theme_id: Theme ID (uses active theme if not provided)

        Returns:
            List of customizer panels
        """
        theme = (
            self.theme_manager.get_theme(theme_id)
            if theme_id
            else self.theme_manager.get_active_theme()
        )

        panels = []

        # Create main panel with default sections
        main_panel = CustomizerPanel(
            id="main",
            title="Customize",
            sections=list(self.DEFAULT_SECTIONS),
        )

        # Add theme-specific sections
        if theme and theme.customizer_sections:
            for section_data in theme.customizer_sections:
                section = self._parse_section(section_data)
                if section:
                    main_panel.sections.append(section)

        # Sort by priority
        main_panel.sections.sort(key=lambda s: s.priority)

        panels.append(main_panel)
        return panels

    def get_values(self, theme_id: str | None = None) -> dict[str, Any]:
        """
        Get current customization values.

        Args:
            theme_id: Theme ID

        Returns:
            Dict of setting_id to value
        """
        values = {}

        # Get defaults from settings
        for panel in self.get_panels(theme_id):
            for section in panel.sections:
                for setting in section.settings:
                    values[setting.id] = setting.default

        # Override with saved customizations
        saved = self.theme_manager.get_customizations(theme_id)
        values.update(saved)

        return values

    def preview(self, setting_id: str, value: Any) -> None:
        """
        Set a preview value (not saved).

        Args:
            setting_id: Setting identifier
            value: Preview value
        """
        self._preview_values[setting_id] = value

    def clear_preview(self) -> None:
        """Clear all preview values."""
        self._preview_values = {}

    def save(
        self,
        values: dict[str, Any],
        theme_id: str | None = None,
    ) -> tuple[bool, str]:
        """
        Save customization values.

        Args:
            values: Dict of setting_id to value
            theme_id: Theme ID

        Returns:
            Tuple of (success, message)
        """
        try:
            # Add to history for undo
            current = self.theme_manager.get_customizations(theme_id)
            self._add_to_history(current)

            # Save to theme manager
            self.theme_manager.set_customizations(values, theme_id)

            # Clear preview
            self.clear_preview()

            logger.info(f"Saved customizations for theme: {theme_id}")
            return True, "Customizations saved"

        except Exception as e:
            logger.exception(f"Failed to save customizations: {e}")
            return False, f"Save failed: {e}"

    def generate_css(
        self,
        theme_id: str | None = None,
        include_preview: bool = False,
    ) -> str:
        """
        Generate CSS from customization values.

        Args:
            theme_id: Theme ID
            include_preview: Include preview values

        Returns:
            Generated CSS string
        """
        values = self.get_values(theme_id)

        if include_preview:
            values.update(self._preview_values)

        css_rules = {}
        custom_css = ""

        for panel in self.get_panels(theme_id):
            for section in panel.sections:
                for setting in section.settings:
                    value = values.get(setting.id, setting.default)

                    if setting.id == "custom_css":
                        custom_css = value or ""
                        continue

                    if not setting.css_property or value is None:
                        continue

                    selector = setting.css_selector or ":root"
                    if selector not in css_rules:
                        css_rules[selector] = {}

                    # Format value
                    if setting.css_template:
                        formatted = setting.css_template.format(value=value)
                    elif setting.type == SettingType.COLOR:
                        formatted = value
                    elif setting.type == SettingType.FONT:
                        formatted = f'"{value}", sans-serif'
                    elif setting.unit:
                        formatted = f"{value}{setting.unit}"
                    else:
                        formatted = str(value)

                    css_rules[selector][setting.css_property] = formatted

        # Build CSS
        css_parts = []

        for selector, properties in css_rules.items():
            if properties:
                prop_lines = [f"  {prop}: {val};" for prop, val in properties.items()]
                css_parts.append(f"{selector} {{\n" + "\n".join(prop_lines) + "\n}")

        # Add custom CSS
        if custom_css:
            css_parts.append(f"\n/* Custom CSS */\n{custom_css}")

        return "\n\n".join(css_parts)

    def generate_font_imports(
        self,
        theme_id: str | None = None,
    ) -> str:
        """
        Generate Google Fonts import CSS.

        Args:
            theme_id: Theme ID

        Returns:
            CSS @import statements
        """
        values = self.get_values(theme_id)
        fonts = set()

        for panel in self.get_panels(theme_id):
            for section in panel.sections:
                for setting in section.settings:
                    if setting.type == SettingType.FONT:
                        font = values.get(setting.id, setting.default)
                        if font and font in self.GOOGLE_FONTS:
                            fonts.add(font)

        if not fonts:
            return ""

        font_params = "|".join(f.replace(" ", "+") + ":400,500,600,700" for f in fonts)
        return (
            f'@import url("https://fonts.googleapis.com/css2?family={font_params}&display=swap");'
        )

    def get_font_choices(self) -> list[dict]:
        """Get available font choices."""
        return [{"value": font, "label": font} for font in self.GOOGLE_FONTS]

    def undo(self, theme_id: str | None = None) -> bool:
        """Undo last change."""
        if self._history_index <= 0:
            return False

        self._history_index -= 1
        values = self._history[self._history_index]
        self.theme_manager.set_customizations(values, theme_id)
        return True

    def redo(self, theme_id: str | None = None) -> bool:
        """Redo last undone change."""
        if self._history_index >= len(self._history) - 1:
            return False

        self._history_index += 1
        values = self._history[self._history_index]
        self.theme_manager.set_customizations(values, theme_id)
        return True

    def can_undo(self) -> bool:
        """Check if undo is available."""
        return self._history_index > 0

    def can_redo(self) -> bool:
        """Check if redo is available."""
        return self._history_index < len(self._history) - 1

    def export_customizations(self, theme_id: str | None = None) -> str:
        """
        Export customizations as JSON.

        Args:
            theme_id: Theme ID

        Returns:
            JSON string
        """
        values = self.get_values(theme_id)
        return json.dumps(
            {
                "theme_id": theme_id,
                "exported_at": utcnow().isoformat(),
                "customizations": values,
            },
            indent=2,
        )

    def import_customizations(
        self,
        data: str,
        theme_id: str | None = None,
    ) -> tuple[bool, str]:
        """
        Import customizations from JSON.

        Args:
            data: JSON string
            theme_id: Theme ID

        Returns:
            Tuple of (success, message)
        """
        try:
            parsed = json.loads(data)
            values = parsed.get("customizations", {})

            return self.save(values, theme_id)

        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {e}"
        except Exception as e:
            return False, f"Import failed: {e}"

    def reset_to_defaults(self, theme_id: str | None = None) -> tuple[bool, str]:
        """
        Reset all customizations to defaults.

        Args:
            theme_id: Theme ID

        Returns:
            Tuple of (success, message)
        """
        # Get default values
        defaults = {}
        for panel in self.get_panels(theme_id):
            for section in panel.sections:
                for setting in section.settings:
                    if setting.default is not None:
                        defaults[setting.id] = setting.default

        return self.save(defaults, theme_id)

    def _parse_section(self, data: dict) -> CustomizerSection | None:
        """Parse a customizer section from dict."""
        if not data.get("id"):
            return None

        settings = []
        for setting_data in data.get("settings", []):
            setting = self._parse_setting(setting_data)
            if setting:
                settings.append(setting)

        return CustomizerSection(
            id=data["id"],
            title=data.get("title", data["id"]),
            description=data.get("description", ""),
            icon=data.get("icon", ""),
            priority=data.get("priority", 50),
            settings=settings,
        )

    def _parse_setting(self, data: dict) -> CustomizerSetting | None:
        """Parse a customizer setting from dict."""
        if not data.get("id"):
            return None

        try:
            setting_type = SettingType(data.get("type", "text"))
        except ValueError:
            setting_type = SettingType.TEXT

        return CustomizerSetting(
            id=data["id"],
            label=data.get("label", data["id"]),
            type=setting_type,
            default=data.get("default"),
            description=data.get("description", ""),
            section=data.get("section", ""),
            choices=data.get("choices", []),
            min=data.get("min"),
            max=data.get("max"),
            step=data.get("step"),
            unit=data.get("unit", ""),
            placeholder=data.get("placeholder", ""),
            required=data.get("required", False),
            pattern=data.get("pattern", ""),
            depends_on=data.get("depends_on"),
            css_property=data.get("css_property", ""),
            css_selector=data.get("css_selector", ""),
            css_template=data.get("css_template", ""),
        )

    def _add_to_history(self, values: dict) -> None:
        """Add values to history for undo."""
        # Remove any redo history
        self._history = self._history[: self._history_index + 1]

        # Add new state
        self._history.append(values.copy())
        self._history_index = len(self._history) - 1

        # Limit history size
        if len(self._history) > 50:
            self._history = self._history[-50:]
            self._history_index = len(self._history) - 1
