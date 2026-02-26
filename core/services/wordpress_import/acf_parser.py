"""ACF Parser - Parses ACF field definitions and PHP serialized data."""

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ACFFieldGroup:
    """Represents an ACF field group."""

    key: str
    title: str
    fields: list["ACFField"]
    location: list[dict] = field(default_factory=list)
    position: str = "normal"
    style: str = "default"
    active: bool = True


@dataclass
class ACFField:
    """Represents an ACF field definition."""

    key: str
    name: str
    label: str
    type: str
    instructions: str = ""
    required: bool = False
    default_value: Any = None
    placeholder: str = ""
    choices: list[dict] = field(default_factory=list)
    min: int | None = None
    max: int | None = None
    min_length: int | None = None
    max_length: int | None = None
    sub_fields: list["ACFField"] = field(default_factory=list)
    layouts: list[dict] = field(default_factory=list)
    conditional_logic: list[dict] = field(default_factory=list)
    wrapper: dict = field(default_factory=dict)


@dataclass
class FocomyField:
    """Focomy field definition."""

    name: str
    type: str
    label: str
    description: str = ""
    required: bool = False
    default: Any = None
    options: list[str] = field(default_factory=list)
    min: int | None = None
    max: int | None = None
    min_length: int | None = None
    max_length: int | None = None
    fields: list["FocomyField"] = field(default_factory=list)
    layouts: list[dict] = field(default_factory=list)
    conditions: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


# ACF to Focomy type mapping
ACF_TYPE_MAP = {
    # Basic
    "text": "string",
    "textarea": "text",
    "number": "integer",
    "range": "integer",
    "email": "email",
    "url": "url",
    "password": "password",
    # Content
    "wysiwyg": "richtext",
    "oembed": "embed",
    # Choice
    "select": "select",
    "checkbox": "multiselect",
    "radio": "select",
    "button_group": "select",
    "true_false": "boolean",
    # Relational
    "link": "link",
    "post_object": "relation",
    "page_link": "relation",
    "relationship": "relation",
    "taxonomy": "taxonomy",
    "user": "user",
    # jQuery
    "google_map": "map",
    "date_picker": "date",
    "date_time_picker": "datetime",
    "time_picker": "time",
    "color_picker": "color",
    # Layout
    "message": "message",
    "accordion": "accordion",
    "tab": "tab",
    "group": "group",
    "repeater": "repeater",
    "flexible_content": "flexible",
    # Media
    "image": "image",
    "file": "file",
    "gallery": "gallery",
    # Pro fields
    "clone": "clone",
}


class ACFParser:
    """
    Parses ACF field group definitions and PHP serialized data.

    Handles:
    - Field group JSON export parsing
    - Individual field parsing with nested support
    - PHP serialized data unserialization
    """

    def parse_field_groups(self, export_data: dict) -> list[ACFFieldGroup]:
        """
        Parse ACF field group export JSON.

        Args:
            export_data: ACF JSON export or array of field groups

        Returns:
            List of parsed ACFFieldGroup objects
        """
        groups = []

        # Handle different export formats
        if isinstance(export_data, list):
            items = export_data
        elif isinstance(export_data, dict):
            items = export_data.get("field_groups", [export_data])
        else:
            return []

        for group_data in items:
            group = self._parse_field_group(group_data)
            if group:
                groups.append(group)

        return groups

    def _parse_field_group(self, data: dict) -> ACFFieldGroup | None:
        """Parse a single field group."""
        if not isinstance(data, dict):
            return None

        key = data.get("key", "")
        if not key:
            return None

        fields = []
        for field_data in data.get("fields", []):
            parsed_field = self._parse_field(field_data)
            if parsed_field:
                fields.append(parsed_field)

        return ACFFieldGroup(
            key=key,
            title=data.get("title", ""),
            fields=fields,
            location=data.get("location", []),
            position=data.get("position", "normal"),
            style=data.get("style", "default"),
            active=data.get("active", True),
        )

    def _parse_field(self, data: dict) -> ACFField | None:
        """Parse a single ACF field."""
        if not isinstance(data, dict):
            return None

        key = data.get("key", "")
        name = data.get("name", "")
        if not key or not name:
            return None

        # Parse choices
        choices = []
        raw_choices = data.get("choices", {})
        if isinstance(raw_choices, dict):
            for value, label in raw_choices.items():
                choices.append({"value": value, "label": label})
        elif isinstance(raw_choices, list):
            choices = raw_choices

        # Parse sub fields (for repeater/group)
        sub_fields = []
        for sub_data in data.get("sub_fields", []):
            sub_field = self._parse_field(sub_data)
            if sub_field:
                sub_fields.append(sub_field)

        # Parse layouts (for flexible content)
        layouts = []
        for layout_data in data.get("layouts", []):
            layout_fields = []
            for field_data in layout_data.get("sub_fields", []):
                parsed = self._parse_field(field_data)
                if parsed:
                    layout_fields.append(parsed)

            layouts.append(
                {
                    "key": layout_data.get("key", ""),
                    "name": layout_data.get("name", ""),
                    "label": layout_data.get("label", ""),
                    "display": layout_data.get("display", "block"),
                    "fields": layout_fields,
                }
            )

        return ACFField(
            key=key,
            name=name,
            label=data.get("label", name),
            type=data.get("type", "text"),
            instructions=data.get("instructions", ""),
            required=bool(data.get("required", False)),
            default_value=data.get("default_value"),
            placeholder=data.get("placeholder", ""),
            choices=choices,
            min=data.get("min"),
            max=data.get("max"),
            min_length=data.get("minlength"),
            max_length=data.get("maxlength"),
            sub_fields=sub_fields,
            layouts=layouts,
            conditional_logic=data.get("conditional_logic", []),
            wrapper=data.get("wrapper", {}),
        )

    def unserialize_php(self, data: str) -> Any:
        """
        Unserialize PHP serialized data.

        Basic implementation for common cases.
        """
        if not data or not isinstance(data, str):
            return data

        # Try JSON first (some plugins use JSON)
        if data.startswith("{") or data.startswith("["):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                pass

        # Simple PHP array unserialization
        if data.startswith("a:"):
            try:
                return self._parse_php_array(data)
            except Exception:
                return data

        return data

    def _parse_php_array(self, data: str) -> Any:
        """Parse PHP serialized array."""
        # Pattern: a:N:{...}
        match = re.match(r"^a:(\d+):\{(.+)\}$", data, re.DOTALL)
        if not match:
            return data

        result = {}
        content = match.group(2)
        pos = 0

        while pos < len(content):
            # Parse key
            key, pos = self._parse_php_value(content, pos)
            if key is None:
                break

            # Parse value
            value, pos = self._parse_php_value(content, pos)

            result[key] = value

        return result

    def _parse_php_value(self, data: str, pos: int) -> tuple[Any, int]:
        """Parse a single PHP serialized value."""
        if pos >= len(data):
            return None, pos

        type_char = data[pos]

        if type_char == "s":
            # String: s:length:"value";
            match = re.match(r's:(\d+):"', data[pos:])
            if match:
                length = int(match.group(1))
                start = pos + len(match.group(0))
                end = start + length
                value = data[start:end]
                return value, end + 2  # Skip ";

        elif type_char == "i":
            # Integer: i:value;
            match = re.match(r"i:(-?\d+);", data[pos:])
            if match:
                return int(match.group(1)), pos + len(match.group(0))

        elif type_char == "d":
            # Double: d:value;
            match = re.match(r"d:([^;]+);", data[pos:])
            if match:
                return float(match.group(1)), pos + len(match.group(0))

        elif type_char == "b":
            # Boolean: b:0; or b:1;
            match = re.match(r"b:([01]);", data[pos:])
            if match:
                return match.group(1) == "1", pos + len(match.group(0))

        elif type_char == "N":
            # Null: N;
            return None, pos + 2

        elif type_char == "a":
            # Array: a:N:{...}
            match = re.match(r"a:(\d+):\{", data[pos:])
            if match:
                count = int(match.group(1))
                inner_pos = pos + len(match.group(0))
                result = {}

                for _ in range(count):
                    key, inner_pos = self._parse_php_value(data, inner_pos)
                    value, inner_pos = self._parse_php_value(data, inner_pos)
                    if key is not None:
                        result[key] = value

                return result, inner_pos + 1  # Skip }

        return None, pos + 1
