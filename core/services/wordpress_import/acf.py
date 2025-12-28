"""ACF Converter - Converts Advanced Custom Fields data to Focomy fields."""

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


class ACFConverter:
    """
    Converts ACF (Advanced Custom Fields) data to Focomy format.

    Handles:
    - Field group definitions
    - Field type conversion
    - Conditional logic
    - Nested fields (repeater, group, flexible content)
    - ACF Pro features
    """

    def __init__(self):
        self._field_groups: list[ACFFieldGroup] = []

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

        self._field_groups = groups
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

    def convert_to_focomy(self, field_groups: list[ACFFieldGroup]) -> list[dict]:
        """
        Convert ACF field groups to Focomy content type definitions.

        Args:
            field_groups: List of ACF field groups

        Returns:
            List of Focomy content type field definitions
        """
        result = []

        for group in field_groups:
            fields = []
            for acf_field in group.fields:
                focomy_field = self._convert_field(acf_field)
                if focomy_field:
                    fields.append(self._field_to_dict(focomy_field))

            result.append(
                {
                    "name": self._slugify(group.title),
                    "label": group.title,
                    "fields": fields,
                    "_acf_key": group.key,
                    "_acf_location": group.location,
                }
            )

        return result

    def _convert_field(self, acf_field: ACFField) -> FocomyField | None:
        """Convert a single ACF field to Focomy field."""
        focomy_type = ACF_TYPE_MAP.get(acf_field.type, "string")

        # Create base field
        focomy_field = FocomyField(
            name=acf_field.name,
            type=focomy_type,
            label=acf_field.label,
            description=acf_field.instructions,
            required=acf_field.required,
            default=acf_field.default_value,
            min=acf_field.min,
            max=acf_field.max,
            min_length=acf_field.min_length,
            max_length=acf_field.max_length,
        )

        # Convert choices
        if acf_field.choices:
            focomy_field.options = [c["value"] for c in acf_field.choices]
            focomy_field.extra["option_labels"] = {
                c["value"]: c["label"] for c in acf_field.choices
            }

        # Convert sub fields (repeater/group)
        if acf_field.sub_fields:
            for sub_field in acf_field.sub_fields:
                converted = self._convert_field(sub_field)
                if converted:
                    focomy_field.fields.append(converted)

        # Convert layouts (flexible content)
        if acf_field.layouts:
            for layout in acf_field.layouts:
                layout_fields = []
                for layout_field in layout.get("fields", []):
                    converted = self._convert_field(layout_field)
                    if converted:
                        layout_fields.append(self._field_to_dict(converted))

                focomy_field.layouts.append(
                    {
                        "name": layout["name"],
                        "label": layout["label"],
                        "fields": layout_fields,
                    }
                )

        # Convert conditional logic
        if acf_field.conditional_logic:
            focomy_field.conditions = self._convert_conditional_logic(acf_field.conditional_logic)

        return focomy_field

    def _convert_conditional_logic(self, acf_logic: list) -> list[dict]:
        """Convert ACF conditional logic to Focomy conditions."""
        conditions = []

        for group in acf_logic:
            if not isinstance(group, list):
                continue

            and_conditions = []
            for rule in group:
                if not isinstance(rule, dict):
                    continue

                field_key = rule.get("field", "")
                operator = rule.get("operator", "==")
                value = rule.get("value", "")

                # Map ACF operators to Focomy
                op_map = {
                    "==": "equals",
                    "!=": "not_equals",
                    "==empty": "empty",
                    "!=empty": "not_empty",
                    "==contains": "contains",
                }

                and_conditions.append(
                    {
                        "field": self._key_to_name(field_key),
                        "operator": op_map.get(operator, "equals"),
                        "value": value,
                    }
                )

            if and_conditions:
                conditions.append({"all": and_conditions})

        return conditions

    def _key_to_name(self, key: str) -> str:
        """Convert ACF field key to field name."""
        # Try to find in parsed field groups
        for group in self._field_groups:
            for acf_field in group.fields:
                if acf_field.key == key:
                    return acf_field.name
        # Fallback: extract name from key
        if key.startswith("field_"):
            return key[6:]
        return key

    def _field_to_dict(self, field: FocomyField) -> dict:
        """Convert FocomyField to dict for YAML output."""
        result = {
            "name": field.name,
            "type": field.type,
            "label": field.label,
        }

        if field.description:
            result["description"] = field.description
        if field.required:
            result["required"] = True
        if field.default is not None:
            result["default"] = field.default
        if field.options:
            result["options"] = field.options
        if field.min is not None:
            result["min"] = field.min
        if field.max is not None:
            result["max"] = field.max
        if field.min_length is not None:
            result["min_length"] = field.min_length
        if field.max_length is not None:
            result["max_length"] = field.max_length
        if field.fields:
            result["fields"] = [self._field_to_dict(f) for f in field.fields]
        if field.layouts:
            result["layouts"] = field.layouts
        if field.conditions:
            result["conditions"] = field.conditions
        if field.extra:
            result.update(field.extra)

        return result

    def _slugify(self, text: str) -> str:
        """Convert text to slug."""
        text = text.lower()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[-\s]+", "_", text)
        return text.strip("_")

    def convert_post_meta(
        self,
        postmeta: dict[str, Any],
        field_groups: list[ACFFieldGroup],
    ) -> dict[str, Any]:
        """
        Convert WordPress post meta to Focomy field values.

        Args:
            postmeta: WordPress post meta dictionary
            field_groups: ACF field group definitions

        Returns:
            Converted field values
        """
        result = {}

        # Build field lookup
        field_lookup = {}
        for group in field_groups:
            for acf_field in group.fields:
                field_lookup[acf_field.name] = acf_field
                # Also add with underscore prefix (ACF stores reference this way)
                field_lookup[f"_{acf_field.name}"] = acf_field

        for key, value in postmeta.items():
            # Skip internal ACF keys
            if key.startswith("_") and key[1:] in field_lookup:
                continue

            if key in field_lookup:
                acf_field = field_lookup[key]
                converted = self._convert_value(value, acf_field)
                result[key] = converted
            else:
                # Keep non-ACF meta as-is
                result[key] = value

        return result

    def _convert_value(self, value: Any, acf_field: ACFField) -> Any:
        """Convert a single ACF field value."""
        if value is None:
            return None

        field_type = acf_field.type

        # Handle serialized PHP data
        if isinstance(value, str) and value.startswith("a:"):
            value = self._unserialize_php(value)

        # Type-specific conversion
        if field_type == "true_false":
            return bool(int(value)) if value else False

        elif field_type in ("number", "range"):
            try:
                return int(value) if "." not in str(value) else float(value)
            except (ValueError, TypeError):
                return 0

        elif field_type == "checkbox":
            if isinstance(value, list):
                return value
            elif isinstance(value, str):
                return [value] if value else []
            return []

        elif field_type == "repeater":
            return self._convert_repeater_value(value, acf_field)

        elif field_type == "flexible_content":
            return self._convert_flexible_value(value, acf_field)

        elif field_type == "group":
            return self._convert_group_value(value, acf_field)

        elif field_type == "gallery":
            if isinstance(value, list):
                return value
            return []

        # Default: return as-is
        return value

    def _convert_repeater_value(self, value: Any, acf_field: ACFField) -> list:
        """Convert repeater field value."""
        if not isinstance(value, (list, int)):
            return []

        # ACF stores row count, actual data is in separate meta keys
        if isinstance(value, int):
            # Row count, we need to reconstruct from sub-field values
            # This is handled at the post level
            return []

        return value

    def _convert_flexible_value(self, value: Any, acf_field: ACFField) -> list:
        """Convert flexible content field value."""
        if not isinstance(value, list):
            return []

        result = []
        for item in value:
            if isinstance(item, dict):
                result.append(item)
        return result

    def _convert_group_value(self, value: Any, acf_field: ACFField) -> dict:
        """Convert group field value."""
        if isinstance(value, dict):
            return value
        return {}

    def _unserialize_php(self, data: str) -> Any:
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


def generate_content_type_yaml(
    field_groups: list[ACFFieldGroup],
    post_type: str = "post",
) -> str:
    """
    Generate Focomy content type YAML from ACF field groups.

    Args:
        field_groups: List of ACF field groups
        post_type: WordPress post type

    Returns:
        YAML string for content type definition
    """
    import yaml

    converter = ACFConverter()
    converted = converter.convert_to_focomy(field_groups)

    # Merge all field groups into one content type
    all_fields = []
    for group in converted:
        all_fields.extend(group["fields"])

    content_type = {
        "name": post_type,
        "label": post_type.replace("_", " ").title(),
        "fields": all_fields,
    }

    return yaml.dump(content_type, allow_unicode=True, default_flow_style=False, sort_keys=False)
