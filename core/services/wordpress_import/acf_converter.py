"""ACF Converter - Converts ACF field data to Focomy format."""

import re
from typing import Any

from .acf_parser import ACF_TYPE_MAP, ACFField, ACFFieldGroup, ACFParser, FocomyField


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
        self._parser = ACFParser()
        self._field_groups: list[ACFFieldGroup] = []

    def parse_field_groups(self, export_data: dict) -> list[ACFFieldGroup]:
        """
        Parse ACF field group export JSON.

        Args:
            export_data: ACF JSON export or array of field groups

        Returns:
            List of parsed ACFFieldGroup objects
        """
        groups = self._parser.parse_field_groups(export_data)
        self._field_groups = groups
        return groups

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
        for group in self._field_groups:
            for acf_field in group.fields:
                if acf_field.key == key:
                    return acf_field.name
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

        field_lookup = {}
        for group in field_groups:
            for acf_field in group.fields:
                field_lookup[acf_field.name] = acf_field
                field_lookup[f"_{acf_field.name}"] = acf_field

        for key, value in postmeta.items():
            if key.startswith("_") and key[1:] in field_lookup:
                continue

            if key in field_lookup:
                acf_field = field_lookup[key]
                converted = self._convert_value(value, acf_field)
                result[key] = converted
            else:
                result[key] = value

        return result

    def _convert_value(self, value: Any, acf_field: ACFField) -> Any:
        """Convert a single ACF field value."""
        if value is None:
            return None

        field_type = acf_field.type

        # Handle serialized PHP data
        if isinstance(value, str) and value.startswith("a:"):
            value = self._parser.unserialize_php(value)

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

        return value

    def _convert_repeater_value(self, value: Any, acf_field: ACFField) -> list:
        """Convert repeater field value."""
        if not isinstance(value, (list, int)):
            return []

        if isinstance(value, int):
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

    all_fields = []
    for group in converted:
        all_fields.extend(group["fields"])

    content_type = {
        "name": post_type,
        "label": post_type.replace("_", " ").title(),
        "fields": all_fields,
    }

    return yaml.dump(content_type, allow_unicode=True, default_flow_style=False, sort_keys=False)
