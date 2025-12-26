"""FieldService - content type definitions and validation."""

from pathlib import Path
from functools import lru_cache
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

from ..config import settings


class FieldDefinition(BaseModel):
    """Field definition from YAML."""
    name: str
    type: str
    label: str = ""
    required: bool = False
    unique: bool = False
    indexed: bool = False
    max_length: Optional[int] = None
    default: Any = None
    options: list[dict[str, str]] = Field(default_factory=list)
    auto_generate: Optional[str] = None
    accept: Optional[str] = None
    multiple: bool = False
    auth_field: bool = False
    suffix: Optional[str] = None


class RelationDefinition(BaseModel):
    """Relation reference in content type."""
    type: str
    label: str = ""
    required: bool = False
    target: Optional[str] = None
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
        """Load all content type and relation definitions."""
        if self._loaded:
            return

        # Load content types
        content_types_dir = settings.base_dir / "content_types"
        if content_types_dir.exists():
            for path in content_types_dir.glob("*.yaml"):
                ct = self._load_content_type(path)
                if ct:
                    self._content_types[ct.name] = ct

        # Load plugin content types
        plugins_dir = settings.base_dir / "plugins"
        if plugins_dir.exists():
            for plugin_dir in plugins_dir.iterdir():
                if plugin_dir.is_dir():
                    ct_dir = plugin_dir / "content_types"
                    if ct_dir.exists():
                        for path in ct_dir.glob("*.yaml"):
                            ct = self._load_content_type(path)
                            if ct:
                                self._content_types[ct.name] = ct

        # Load relations
        relations_path = settings.base_dir / "relations.yaml"
        if relations_path.exists():
            self._load_relations(relations_path)

        # Load plugin relations
        if plugins_dir.exists():
            for plugin_dir in plugins_dir.iterdir():
                if plugin_dir.is_dir():
                    rel_path = plugin_dir / "relations.yaml"
                    if rel_path.exists():
                        self._load_relations(rel_path)

        self._loaded = True

    def _load_content_type(self, path: Path) -> Optional[ContentType]:
        """Load a single content type from YAML."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data:
                    return ContentType(**data)
        except Exception as e:
            print(f"Error loading content type {path}: {e}")
        return None

    def _load_relations(self, path: Path):
        """Load relation definitions from YAML."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data:
                    for name, rel_data in data.items():
                        rel_data["from"] = rel_data.pop("from", "")
                        rel_data["to"] = rel_data.pop("to", "")
                        self._relation_types[name] = RelationTypeDefinition(**rel_data)
        except Exception as e:
            print(f"Error loading relations {path}: {e}")

    def get_content_type(self, type_name: str) -> Optional[ContentType]:
        """Get content type definition by name."""
        self._load_all()
        return self._content_types.get(type_name)

    def get_all_content_types(self) -> dict[str, ContentType]:
        """Get all content type definitions."""
        self._load_all()
        return self._content_types.copy()

    def get_relation_type(self, relation_name: str) -> Optional[RelationTypeDefinition]:
        """Get relation type definition by name."""
        self._load_all()
        return self._relation_types.get(relation_name)

    def get_all_relation_types(self) -> dict[str, RelationTypeDefinition]:
        """Get all relation type definitions."""
        self._load_all()
        return self._relation_types.copy()

    def validate(self, type_name: str, data: dict[str, Any]) -> ValidationResult:
        """Validate data against content type definition."""
        self._load_all()

        ct = self._content_types.get(type_name)
        if not ct:
            return ValidationResult(
                valid=False,
                errors=[ValidationError(field="type", message=f"Unknown content type: {type_name}")]
            )

        errors = []

        for field in ct.fields:
            value = data.get(field.name)

            # Required check
            if field.required and (value is None or value == ""):
                errors.append(ValidationError(
                    field=field.name,
                    message=f"{field.label or field.name} is required"
                ))
                continue

            if value is None:
                continue

            # Type-specific validation
            if field.type == "string" and field.max_length:
                if isinstance(value, str) and len(value) > field.max_length:
                    errors.append(ValidationError(
                        field=field.name,
                        message=f"{field.label or field.name} must be {field.max_length} characters or less"
                    ))

            elif field.type == "email":
                if isinstance(value, str) and "@" not in value:
                    errors.append(ValidationError(
                        field=field.name,
                        message=f"{field.label or field.name} must be a valid email"
                    ))

            elif field.type == "select":
                valid_values = [opt.get("value") for opt in field.options]
                if value not in valid_values:
                    errors.append(ValidationError(
                        field=field.name,
                        message=f"{field.label or field.name} must be one of: {', '.join(valid_values)}"
                    ))

            elif field.type == "integer":
                if not isinstance(value, int):
                    try:
                        int(value)
                    except (ValueError, TypeError):
                        errors.append(ValidationError(
                            field=field.name,
                            message=f"{field.label or field.name} must be an integer"
                        ))

        return ValidationResult(valid=len(errors) == 0, errors=errors)

    def get_field_type(self, field_def: FieldDefinition) -> str:
        """Get the storage column type for a field."""
        type_mapping = {
            "string": "text",
            "text": "text",
            "slug": "text",
            "email": "text",
            "url": "text",
            "integer": "int",
            "float": "float",
            "boolean": "int",
            "datetime": "datetime",
            "date": "datetime",
            "select": "text",
            "multiselect": "json",
            "blocks": "json",
            "media": "text",
            "json": "json",
        }
        return type_mapping.get(field_def.type, "text")


# Singleton instance
@lru_cache
def get_field_service() -> FieldService:
    return FieldService()


field_service = get_field_service()
