"""FieldService - content type definitions and validation."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
import yaml
from pydantic import BaseModel, Field

from ..config import settings

logger = structlog.get_logger(__name__)

# Email regex pattern (RFC 5322 simplified)
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# URL regex pattern
URL_PATTERN = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)

# Phone number pattern (international format)
PHONE_PATTERN = re.compile(r"^[\+]?[(]?[0-9]{1,4}[)]?[-\s\./0-9]*$")

# Slug pattern
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Color pattern (#RGB, #RRGGBB, #RRGGBBAA)
COLOR_PATTERN = re.compile(r"^#([A-Fa-f0-9]{3}|[A-Fa-f0-9]{6}|[A-Fa-f0-9]{8})$")


class FieldDefinition(BaseModel):
    """Field definition from YAML."""

    name: str
    type: str
    label: str = ""
    required: bool = False
    unique: bool = False
    indexed: bool = False
    max_length: int | None = None
    min_length: int | None = None
    default: Any = None
    options: list[dict[str, str]] = Field(default_factory=list)
    auto_generate: str | None = None
    accept: str | None = None
    multiple: bool = False
    auth_field: bool = False
    suffix: str | None = None
    # Extended properties for Content Builder
    description: str | None = None
    hint: str | None = None
    placeholder: str | None = None
    help: str | None = None
    pattern: str | None = None  # Regex pattern validation
    min: float | None = None  # Min value for numbers
    max: float | None = None  # Max value for numbers
    step: float | None = None  # Step for number input
    decimal_places: int | None = None  # For decimal/money fields
    max_items: int | None = None  # For arrays/galleries
    min_items: int | None = None  # For arrays/galleries
    # Admin UI options
    admin_hidden: bool = False
    admin_only: bool = False
    admin_readonly: bool = False
    sidebar: bool = False  # Show in sidebar (right column) in edit form
    show_in_list: bool = False  # Show in admin list view
    searchable: bool = False  # Include in search
    # Conditional logic
    conditions: dict | None = None  # {show: [...], required: [...]}
    # Permissions
    permissions: dict | None = None  # {read: [...], write: [...]}
    # Calculated/lookup fields
    formula: str | None = None  # For calculated fields
    formula_timing: str = "save"  # When to calculate: "save" or "display"
    source: str | None = None  # For lookup fields (relation name)
    source_field: str | None = None  # Field to lookup from related entity
    format: str | None = None  # Display format (currency, percent, etc.)
    # Repeater/flexible content
    fields: list["FieldDefinition"] = Field(default_factory=list)  # Sub-fields
    layouts: list[dict] = Field(default_factory=list)  # For flexible content
    # Validation rules
    validation: list[dict] = Field(default_factory=list)  # Custom validation rules
    # Status field transitions (for select fields with status-like behavior)
    # Format: {"draft": ["published"], "published": ["draft", "archived"]}
    transitions: dict[str, list[str]] | None = None

    def is_transition_allowed(self, from_value: str, to_value: str) -> bool:
        """Check if a status transition is allowed.

        If transitions is not defined, all transitions are allowed.
        """
        if self.transitions is None:
            return True
        if from_value == to_value:
            return True
        allowed = self.transitions.get(from_value, [])
        return to_value in allowed


class RelationDefinition(BaseModel):
    """Relation reference in content type."""

    type: str
    label: str = ""
    required: bool = False
    target: str | None = None
    self_referential: bool = False


class ContentType(BaseModel):
    """Content type definition."""

    name: str
    label: str = ""
    label_plural: str = ""
    icon: str = "document"
    admin_menu: bool = True
    searchable: bool = False
    hierarchical: bool = False
    auth_entity: bool = False
    # URL routing
    path_prefix: str = ""  # e.g., "/news", "/blog", "/docs"
    slug_field: str = "slug"  # Field to use for URL slug
    template: str = ""  # Custom template (defaults to {name}.html or post.html)
    # Listing
    archive_enabled: bool = False  # Enable /archive/{year}/{month}
    feed_enabled: bool = False  # Enable RSS feed
    # Menu
    menu_linkable: bool = False  # Can be linked from menu items
    fields: list[FieldDefinition] = Field(default_factory=list)
    relations: list[RelationDefinition] = Field(default_factory=list)


class RelationTypeDefinition(BaseModel):
    """Global relation type definition."""

    from_type: str = Field(alias="from")
    to_type: str = Field(alias="to")
    type: str  # many_to_one, many_to_many, one_to_one
    label: str = ""
    required: bool = False
    self_referential: bool = False
    cascade_delete: bool = False  # If true, soft-delete from_entity when to_entity is deleted


class ValidationError(BaseModel):
    """Validation error."""

    field: str
    message: str


class ValidationResult(BaseModel):
    """Validation result."""

    valid: bool
    errors: list[ValidationError] = Field(default_factory=list)


class FieldService:
    """
    Field definition service.

    Loads content type definitions from YAML files.
    Validates data against field definitions.
    """

    def __init__(self):
        self._content_types: dict[str, ContentType] = {}
        self._relation_types: dict[str, RelationTypeDefinition] = {}
        self._loaded = False

    def _load_all(self):
        """Load all content type and relation definitions.

        Architecture:
        1. Core content_types: Always loaded from package (non-overridable)
        2. Plugin content_types: Additive only (cannot override core)
        3. Core relations: Always loaded from package (non-overridable)
        4. Plugin relations: Additive only (cannot override core)
        """
        if self._loaded:
            return

        # Core directory (package内、単一情報源)
        core_dir = Path(__file__).parent.parent

        # 1. Load core content_types from package (常に読み込み、上書き不可)
        core_ct_dir = core_dir / "content_types"
        if core_ct_dir.exists():
            for path in core_ct_dir.glob("*.yaml"):
                ct = self._load_content_type(path)
                if ct:
                    self._content_types[ct.name] = ct
                    logger.debug("core_content_type_loaded", name=ct.name)

        # 2. Load plugin content_types (追加のみ、コア上書き禁止)
        plugins_dir = settings.base_dir / "plugins"
        if plugins_dir.exists():
            for plugin_dir in plugins_dir.iterdir():
                if plugin_dir.is_dir():
                    ct_dir = plugin_dir / "content_types"
                    if ct_dir.exists():
                        for path in ct_dir.glob("*.yaml"):
                            ct = self._load_content_type(path)
                            if ct:
                                if ct.name in self._content_types:
                                    logger.warning(
                                        "plugin_cannot_override_core",
                                        plugin=plugin_dir.name,
                                        content_type=ct.name,
                                    )
                                    continue  # コア上書き禁止
                                self._content_types[ct.name] = ct
                                logger.debug(
                                    "plugin_content_type_loaded",
                                    plugin=plugin_dir.name,
                                    name=ct.name,
                                )

        # 3. Load core relations from package (常に読み込み)
        core_relations = core_dir / "relations.yaml"
        if core_relations.exists():
            self._load_relations(core_relations, is_core=True)

        # 4. Load plugin relations (追加のみ、コア上書き禁止)
        if plugins_dir.exists():
            for plugin_dir in plugins_dir.iterdir():
                if plugin_dir.is_dir():
                    rel_path = plugin_dir / "relations.yaml"
                    if rel_path.exists():
                        self._load_relations(rel_path, is_core=False, plugin_name=plugin_dir.name)

        self._loaded = True

    def _load_content_type(self, path: Path) -> ContentType | None:
        """Load a single content type from YAML."""
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data:
                    return ContentType(**data)
        except Exception as e:
            print(f"Error loading content type {path}: {e}")
        return None

    def _load_relations(self, path: Path, is_core: bool = True, plugin_name: str | None = None):
        """Load relation definitions from YAML.

        Args:
            path: Path to relations.yaml
            is_core: If True, these are core relations (always loaded)
            plugin_name: Name of the plugin (for logging)
        """
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data:
                    for name, rel_data in data.items():
                        # プラグインからのコア上書き禁止
                        if not is_core and name in self._relation_types:
                            logger.warning(
                                "plugin_cannot_override_core_relation",
                                plugin=plugin_name,
                                relation=name,
                            )
                            continue
                        rel_data["from"] = rel_data.pop("from", "")
                        rel_data["to"] = rel_data.pop("to", "")
                        self._relation_types[name] = RelationTypeDefinition(**rel_data)
                        if is_core:
                            logger.debug("core_relation_loaded", name=name)
                        else:
                            logger.debug("plugin_relation_loaded", plugin=plugin_name, name=name)
        except Exception as e:
            logger.error("error_loading_relations", path=str(path), error=str(e))

    def get_content_type(self, type_name: str) -> ContentType | None:
        """Get content type definition by name."""
        self._load_all()
        return self._content_types.get(type_name)

    def get_all_content_types(self) -> dict[str, ContentType]:
        """Get all content type definitions."""
        self._load_all()
        return self._content_types.copy()

    def get_relation_type(self, relation_name: str) -> RelationTypeDefinition | None:
        """Get relation type definition by name."""
        self._load_all()
        return self._relation_types.get(relation_name)

    def get_all_relation_types(self) -> dict[str, RelationTypeDefinition]:
        """Get all relation type definitions."""
        self._load_all()
        return self._relation_types.copy()

    def get_cascade_relations_for_type(
        self, to_type: str
    ) -> list[tuple[str, RelationTypeDefinition]]:
        """Get relations that cascade delete when the target type is deleted.

        Args:
            to_type: The entity type being deleted

        Returns:
            List of (relation_name, relation_def) tuples for relations
            that have cascade_delete=True and point TO this type
        """
        self._load_all()
        result = []
        for name, rel_def in self._relation_types.items():
            if rel_def.to_type == to_type and rel_def.cascade_delete:
                result.append((name, rel_def))
        return result

    def validate(
        self, type_name: str, data: dict[str, Any], context: dict = None
    ) -> ValidationResult:
        """Validate data against content type definition.

        Args:
            type_name: Content type name
            data: Data to validate
            context: Optional context for conditional validation

        Returns:
            ValidationResult with valid flag and errors list
        """
        self._load_all()

        ct = self._content_types.get(type_name)
        if not ct:
            return ValidationResult(
                valid=False,
                errors=[
                    ValidationError(field="type", message=f"Unknown content type: {type_name}")
                ],
            )

        errors = []
        context = context or data

        for field in ct.fields:
            field_errors = self._validate_field(field, data.get(field.name), context)
            errors.extend(field_errors)

        return ValidationResult(valid=len(errors) == 0, errors=errors)

    def _validate_field(
        self, field: FieldDefinition, value: Any, context: dict
    ) -> list[ValidationError]:
        """Validate a single field value."""
        errors = []
        label = field.label or field.name

        # Check conditional required
        is_required = field.required
        if field.conditions and "required" in field.conditions:
            is_required = self._evaluate_conditions(field.conditions["required"], context)

        # Check conditional show (if not shown, skip validation)
        if field.conditions and "show" in field.conditions:
            if not self._evaluate_conditions(field.conditions["show"], context):
                return []  # Field is hidden, skip validation

        # Required check
        if is_required and (value is None or value == "" or value == []):
            errors.append(ValidationError(field=field.name, message=f"{label} is required"))
            return errors

        if value is None or value == "":
            return errors

        # String length validation
        if isinstance(value, str):
            if field.min_length and len(value) < field.min_length:
                errors.append(
                    ValidationError(
                        field=field.name,
                        message=f"{label} must be at least {field.min_length} characters",
                    )
                )
            if field.max_length and len(value) > field.max_length:
                errors.append(
                    ValidationError(
                        field=field.name,
                        message=f"{label} must be {field.max_length} characters or less",
                    )
                )

        # Pattern validation
        if field.pattern and isinstance(value, str):
            try:
                if not re.match(field.pattern, value):
                    errors.append(
                        ValidationError(field=field.name, message=f"{label} format is invalid")
                    )
            except re.error:
                pass  # Invalid pattern, skip

        # Type-specific validation
        type_validators = {
            "email": self._validate_email,
            "url": self._validate_url,
            "phone": self._validate_phone,
            "slug": self._validate_slug,
            "color": self._validate_color,
            "integer": self._validate_integer,
            "number": self._validate_integer,
            "float": self._validate_float,
            "decimal": self._validate_float,
            "money": self._validate_float,
            "range": self._validate_float,
            "select": self._validate_select,
            "radio": self._validate_select,
            "button_group": self._validate_select,
            "multiselect": self._validate_multiselect,
            "checkbox": self._validate_multiselect,
            "tags": self._validate_array,
            "gallery": self._validate_array,
            "repeater": self._validate_repeater,
            "group": self._validate_group,
        }

        validator = type_validators.get(field.type)
        if validator:
            type_errors = validator(field, value)
            errors.extend(type_errors)

        # Min/max validation for numbers
        if field.type in ("integer", "number", "float", "decimal", "money", "range"):
            num_value = self._to_number(value)
            if num_value is not None:
                if field.min is not None and num_value < field.min:
                    errors.append(
                        ValidationError(
                            field=field.name, message=f"{label} must be at least {field.min}"
                        )
                    )
                if field.max is not None and num_value > field.max:
                    errors.append(
                        ValidationError(
                            field=field.name, message=f"{label} must be at most {field.max}"
                        )
                    )

        # Array length validation
        if isinstance(value, list):
            if field.min_items is not None and len(value) < field.min_items:
                errors.append(
                    ValidationError(
                        field=field.name,
                        message=f"{label} must have at least {field.min_items} items",
                    )
                )
            if field.max_items is not None and len(value) > field.max_items:
                errors.append(
                    ValidationError(
                        field=field.name,
                        message=f"{label} must have at most {field.max_items} items",
                    )
                )

        # Custom validation rules
        for rule in field.validation:
            rule_error = self._apply_validation_rule(field, value, rule, context)
            if rule_error:
                errors.append(rule_error)

        return errors

    def _evaluate_conditions(self, conditions: list[dict], context: dict) -> bool:
        """Evaluate conditional logic rules."""
        if not conditions:
            return True

        for condition in conditions:
            field_name = condition.get("field")
            operator = condition.get("operator", "equals")
            expected = condition.get("value")
            actual = context.get(field_name)

            result = self._evaluate_operator(actual, operator, expected)
            if not result:
                return False

        return True

    def _evaluate_operator(self, actual: Any, operator: str, expected: Any) -> bool:
        """Evaluate a single condition operator."""
        operators = {
            "equals": lambda a, b: a == b,
            "not_equals": lambda a, b: a != b,
            "contains": lambda a, b: b in str(a) if a else False,
            "not_contains": lambda a, b: b not in str(a) if a else True,
            "starts_with": lambda a, b: str(a).startswith(str(b)) if a else False,
            "ends_with": lambda a, b: str(a).endswith(str(b)) if a else False,
            "greater_than": lambda a, b: float(a) > float(b) if a else False,
            "less_than": lambda a, b: float(a) < float(b) if a else False,
            "greater_equal": lambda a, b: float(a) >= float(b) if a else False,
            "less_equal": lambda a, b: float(a) <= float(b) if a else False,
            "is_empty": lambda a, _: not a,
            "is_not_empty": lambda a, _: bool(a),
            "in": lambda a, b: a in b if isinstance(b, (list, tuple)) else False,
            "not_in": lambda a, b: a not in b if isinstance(b, (list, tuple)) else True,
        }

        op_func = operators.get(operator, lambda a, b: a == b)
        try:
            return op_func(actual, expected)
        except (ValueError, TypeError):
            return False

    def _validate_email(self, field: FieldDefinition, value: Any) -> list[ValidationError]:
        """Validate email format."""
        if isinstance(value, str) and value:
            if not EMAIL_PATTERN.match(value):
                return [
                    ValidationError(
                        field=field.name,
                        message=f"{field.label or field.name} must be a valid email address",
                    )
                ]
        return []

    def _validate_url(self, field: FieldDefinition, value: Any) -> list[ValidationError]:
        """Validate URL format."""
        if isinstance(value, str) and value:
            if not URL_PATTERN.match(value):
                return [
                    ValidationError(
                        field=field.name, message=f"{field.label or field.name} must be a valid URL"
                    )
                ]
        return []

    def _validate_phone(self, field: FieldDefinition, value: Any) -> list[ValidationError]:
        """Validate phone number format."""
        if isinstance(value, str) and value:
            if not PHONE_PATTERN.match(value):
                return [
                    ValidationError(
                        field=field.name,
                        message=f"{field.label or field.name} must be a valid phone number",
                    )
                ]
        return []

    def _validate_slug(self, field: FieldDefinition, value: Any) -> list[ValidationError]:
        """Validate slug format."""
        if isinstance(value, str) and value:
            if not SLUG_PATTERN.match(value):
                return [
                    ValidationError(
                        field=field.name,
                        message=f"{field.label or field.name} must contain only lowercase letters, numbers, and hyphens",
                    )
                ]
        return []

    def _validate_color(self, field: FieldDefinition, value: Any) -> list[ValidationError]:
        """Validate color format."""
        if isinstance(value, str) and value:
            if not COLOR_PATTERN.match(value):
                return [
                    ValidationError(
                        field=field.name,
                        message=f"{field.label or field.name} must be a valid color code (e.g., #FF0000)",
                    )
                ]
        return []

    def _validate_integer(self, field: FieldDefinition, value: Any) -> list[ValidationError]:
        """Validate integer type."""
        if not isinstance(value, int):
            try:
                int(value)
            except (ValueError, TypeError):
                return [
                    ValidationError(
                        field=field.name, message=f"{field.label or field.name} must be an integer"
                    )
                ]
        return []

    def _validate_float(self, field: FieldDefinition, value: Any) -> list[ValidationError]:
        """Validate float type."""
        if not isinstance(value, (int, float)):
            try:
                float(value)
            except (ValueError, TypeError):
                return [
                    ValidationError(
                        field=field.name, message=f"{field.label or field.name} must be a number"
                    )
                ]
        return []

    def _validate_select(self, field: FieldDefinition, value: Any) -> list[ValidationError]:
        """Validate select field."""
        if not field.options:
            return []
        valid_values = [opt.get("value") for opt in field.options]
        if value not in valid_values:
            return [
                ValidationError(
                    field=field.name,
                    message=f"{field.label or field.name} must be one of: {', '.join(str(v) for v in valid_values)}",
                )
            ]
        return []

    def _validate_multiselect(self, field: FieldDefinition, value: Any) -> list[ValidationError]:
        """Validate multiselect field."""
        if not isinstance(value, list):
            return [
                ValidationError(
                    field=field.name, message=f"{field.label or field.name} must be a list"
                )
            ]
        if not field.options:
            return []
        valid_values = [opt.get("value") for opt in field.options]
        for v in value:
            if v not in valid_values:
                return [
                    ValidationError(
                        field=field.name,
                        message=f"{field.label or field.name} contains invalid value: {v}",
                    )
                ]
        return []

    def _validate_array(self, field: FieldDefinition, value: Any) -> list[ValidationError]:
        """Validate array field."""
        if not isinstance(value, list):
            return [
                ValidationError(
                    field=field.name, message=f"{field.label or field.name} must be a list"
                )
            ]
        return []

    def _validate_repeater(self, field: FieldDefinition, value: Any) -> list[ValidationError]:
        """Validate repeater field with nested fields."""
        errors = []
        if not isinstance(value, list):
            return [
                ValidationError(
                    field=field.name, message=f"{field.label or field.name} must be a list"
                )
            ]

        if not field.fields:
            return []

        for i, row in enumerate(value):
            if not isinstance(row, dict):
                errors.append(
                    ValidationError(field=f"{field.name}[{i}]", message="Row must be an object")
                )
                continue

            for sub_field in field.fields:
                sub_errors = self._validate_field(sub_field, row.get(sub_field.name), row)
                for err in sub_errors:
                    errors.append(
                        ValidationError(field=f"{field.name}[{i}].{err.field}", message=err.message)
                    )

        return errors

    def _validate_group(self, field: FieldDefinition, value: Any) -> list[ValidationError]:
        """Validate group field with nested fields."""
        errors = []
        if not isinstance(value, dict):
            return [
                ValidationError(
                    field=field.name, message=f"{field.label or field.name} must be an object"
                )
            ]

        if not field.fields:
            return []

        for sub_field in field.fields:
            sub_errors = self._validate_field(sub_field, value.get(sub_field.name), value)
            for err in sub_errors:
                errors.append(
                    ValidationError(field=f"{field.name}.{err.field}", message=err.message)
                )

        return errors

    def _apply_validation_rule(
        self, field: FieldDefinition, value: Any, rule: dict, context: dict
    ) -> ValidationError | None:
        """Apply a custom validation rule."""
        rule_type = rule.get("rule")
        rule_value = rule.get("value")
        message = rule.get("message", f"{field.label or field.name} validation failed")

        if rule_type == "unique":
            # Unique validation is handled at the service level
            pass
        elif rule_type == "before":
            # Date before another field
            compare_field = rule.get("field")
            compare_value = context.get(compare_field)
            if value and compare_value and str(value) >= str(compare_value):
                return ValidationError(field=field.name, message=message)
        elif rule_type == "after":
            # Date after another field
            compare_field = rule.get("field")
            compare_value = context.get(compare_field)
            if value and compare_value and str(value) <= str(compare_value):
                return ValidationError(field=field.name, message=message)
        elif rule_type == "pattern":
            # Custom regex pattern
            if isinstance(value, str) and rule_value:
                try:
                    if not re.match(rule_value, value):
                        return ValidationError(field=field.name, message=message)
                except re.error:
                    pass
        elif rule_type == "min":
            num_value = self._to_number(value)
            if num_value is not None and num_value < float(rule_value):
                return ValidationError(field=field.name, message=message)
        elif rule_type == "max":
            num_value = self._to_number(value)
            if num_value is not None and num_value > float(rule_value):
                return ValidationError(field=field.name, message=message)

        return None

    def _to_number(self, value: Any) -> float | None:
        """Convert value to number."""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None

    def get_field_type(self, field_def: FieldDefinition) -> str:
        """Get the storage column type for a field."""
        type_mapping = {
            # Basic text fields
            "string": "text",
            "text": "text",
            "slug": "text",
            "email": "text",
            "url": "text",
            "phone": "text",
            "color": "text",
            "password": "text",
            # Numbers
            "integer": "int",
            "number": "int",
            "float": "float",
            "decimal": "float",
            "money": "float",
            "range": "float",
            # Boolean
            "boolean": "int",
            # Date/time
            "datetime": "datetime",
            "date": "datetime",
            "time": "text",
            # Select
            "select": "text",
            "radio": "text",
            "button_group": "text",
            "multiselect": "json",
            "checkbox": "json",
            "tags": "json",
            # Rich content
            "blocks": "json",
            "markdown": "text",
            "wysiwyg": "text",
            "code": "text",
            # Media
            "media": "text",
            "image": "text",
            "file": "text",
            "video": "text",
            "audio": "text",
            "svg": "text",
            "gallery": "json",
            # Relations
            "relation": "text",
            "relations": "json",
            "taxonomy": "json",
            "user": "text",
            # Structure
            "repeater": "json",
            "flexible": "json",
            "group": "json",
            # Special
            "json": "json",
            "map": "json",
            "address": "json",
            "link": "json",
            "oembed": "text",
            "hidden": "text",
            "calculated": "text",  # Stored as computed value
            "lookup": "text",  # Stored as cached value
        }
        return type_mapping.get(field_def.type, "text")


# Singleton instance
@lru_cache
def get_field_service() -> FieldService:
    return FieldService()


field_service = get_field_service()
