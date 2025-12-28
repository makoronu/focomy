"""Tests for FieldService.

Tests content type loading and validation.
"""

import pytest
from pathlib import Path

from core.services.field import FieldService, ContentType, FieldDefinition, ValidationResult


class TestFieldServiceBasic:
    """Basic FieldService functionality tests."""

    @pytest.fixture
    def field_service(self) -> FieldService:
        return FieldService()

    def test_field_service_init(self, field_service: FieldService):
        """Test FieldService initialization."""
        assert field_service is not None
        assert field_service._content_types == {}
        assert field_service._loaded is False

    def test_get_content_type_loads_on_demand(self, field_service: FieldService):
        """Test that content types are loaded on first access."""
        # Before access, not loaded
        assert field_service._loaded is False

        # Access triggers loading
        ct = field_service.get_content_type("post")

        # Now loaded
        assert field_service._loaded is True

    def test_get_all_content_types(self, field_service: FieldService):
        """Test getting all content types."""
        content_types = field_service.get_all_content_types()

        # Should return a copy
        assert isinstance(content_types, dict)


class TestContentTypeModel:
    """Tests for ContentType model."""

    def test_content_type_defaults(self):
        """Test ContentType default values."""
        ct = ContentType(name="test")

        assert ct.name == "test"
        assert ct.label == ""
        assert ct.icon == "document"
        assert ct.admin_menu is True
        assert ct.searchable is False
        assert ct.hierarchical is False
        assert ct.fields == []
        assert ct.relations == []

    def test_content_type_with_fields(self):
        """Test ContentType with fields."""
        ct = ContentType(
            name="post",
            label="Post",
            fields=[
                FieldDefinition(name="title", type="text", required=True),
                FieldDefinition(name="slug", type="slug", unique=True),
            ]
        )

        assert len(ct.fields) == 2
        assert ct.fields[0].name == "title"
        assert ct.fields[0].required is True
        assert ct.fields[1].name == "slug"
        assert ct.fields[1].unique is True


class TestFieldDefinitionModel:
    """Tests for FieldDefinition model."""

    def test_field_definition_defaults(self):
        """Test FieldDefinition default values."""
        field = FieldDefinition(name="test", type="text")

        assert field.name == "test"
        assert field.type == "text"
        assert field.label == ""
        assert field.required is False
        assert field.unique is False
        assert field.indexed is False
        assert field.default is None
        assert field.options == []

    def test_field_definition_with_options(self):
        """Test FieldDefinition with options."""
        field = FieldDefinition(
            name="status",
            type="select",
            options=[
                {"value": "draft", "label": "Draft"},
                {"value": "published", "label": "Published"},
            ]
        )

        assert len(field.options) == 2
        assert field.options[0]["value"] == "draft"

    def test_field_definition_transitions(self):
        """Test field status transitions."""
        field = FieldDefinition(
            name="status",
            type="select",
            transitions={
                "draft": ["published"],
                "published": ["draft", "archived"],
                "archived": [],
            }
        )

        # Allowed transitions
        assert field.is_transition_allowed("draft", "published") is True
        assert field.is_transition_allowed("published", "draft") is True
        assert field.is_transition_allowed("published", "archived") is True

        # Not allowed transitions
        assert field.is_transition_allowed("draft", "archived") is False
        assert field.is_transition_allowed("archived", "draft") is False

        # Same value always allowed
        assert field.is_transition_allowed("draft", "draft") is True

    def test_field_definition_no_transitions(self):
        """Test that all transitions allowed when not defined."""
        field = FieldDefinition(name="status", type="select")

        # All transitions allowed when not defined
        assert field.is_transition_allowed("any", "value") is True
        assert field.is_transition_allowed("draft", "published") is True


class TestValidationResult:
    """Tests for ValidationResult model."""

    def test_valid_result(self):
        """Test valid validation result."""
        result = ValidationResult(valid=True)

        assert result.valid is True
        assert result.errors == []

    def test_invalid_result(self):
        """Test invalid validation result with errors."""
        from core.services.field import ValidationError

        result = ValidationResult(
            valid=False,
            errors=[
                ValidationError(field="title", message="Title is required"),
            ]
        )

        assert result.valid is False
        assert len(result.errors) == 1
        assert result.errors[0].field == "title"


class TestFieldTypeMapping:
    """Tests for field type to storage type mapping."""

    @pytest.fixture
    def field_service(self) -> FieldService:
        return FieldService()

    def test_text_fields_map_to_text(self, field_service: FieldService):
        """Test text-like fields map to text storage."""
        text_types = ["string", "text", "slug", "email", "url", "phone", "color", "password"]

        for field_type in text_types:
            field = FieldDefinition(name="test", type=field_type)
            storage = field_service.get_field_type(field)
            assert storage == "text", f"{field_type} should map to text"

    def test_number_fields_map_to_int(self, field_service: FieldService):
        """Test number fields map to int storage."""
        int_types = ["integer", "number"]

        for field_type in int_types:
            field = FieldDefinition(name="test", type=field_type)
            storage = field_service.get_field_type(field)
            assert storage == "int", f"{field_type} should map to int"

    def test_float_fields_map_to_float(self, field_service: FieldService):
        """Test float fields map to float storage."""
        float_types = ["float", "decimal", "money", "range"]

        for field_type in float_types:
            field = FieldDefinition(name="test", type=field_type)
            storage = field_service.get_field_type(field)
            assert storage == "float", f"{field_type} should map to float"

    def test_json_fields_map_to_json(self, field_service: FieldService):
        """Test JSON fields map to json storage."""
        json_types = ["blocks", "multiselect", "checkbox", "tags", "gallery", "repeater", "json"]

        for field_type in json_types:
            field = FieldDefinition(name="test", type=field_type)
            storage = field_service.get_field_type(field)
            assert storage == "json", f"{field_type} should map to json"

    def test_datetime_fields_map_to_datetime(self, field_service: FieldService):
        """Test datetime fields map to datetime storage."""
        dt_types = ["datetime", "date"]

        for field_type in dt_types:
            field = FieldDefinition(name="test", type=field_type)
            storage = field_service.get_field_type(field)
            assert storage == "datetime", f"{field_type} should map to datetime"

    def test_unknown_type_maps_to_text(self, field_service: FieldService):
        """Test unknown field types default to text."""
        field = FieldDefinition(name="test", type="unknown_type")
        storage = field_service.get_field_type(field)
        assert storage == "text"
