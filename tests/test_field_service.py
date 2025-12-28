"""Tests for FieldService.

Tests field validation, serialization, and formula computation.
"""

import pytest
from datetime import datetime, date

from core.services.field import FieldService


class TestFieldValidation:
    """Field validation test cases."""

    @pytest.fixture
    def field_service(self) -> FieldService:
        return FieldService()

    def test_validate_required_field(self, field_service: FieldService):
        """Test required field validation."""
        field_def = {
            "name": "title",
            "type": "text",
            "required": True,
        }

        # Valid
        assert field_service.validate_field(field_def, "Hello") is True

        # Invalid - empty
        with pytest.raises(ValueError, match="required"):
            field_service.validate_field(field_def, "")

        # Invalid - None
        with pytest.raises(ValueError, match="required"):
            field_service.validate_field(field_def, None)

    def test_validate_text_field(self, field_service: FieldService):
        """Test text field validation."""
        field_def = {
            "name": "title",
            "type": "text",
            "min_length": 3,
            "max_length": 100,
        }

        # Valid
        assert field_service.validate_field(field_def, "Hello World") is True

        # Too short
        with pytest.raises(ValueError, match="min"):
            field_service.validate_field(field_def, "Hi")

        # Too long
        with pytest.raises(ValueError, match="max"):
            field_service.validate_field(field_def, "x" * 101)

    def test_validate_number_field(self, field_service: FieldService):
        """Test number field validation."""
        field_def = {
            "name": "count",
            "type": "number",
            "min": 0,
            "max": 100,
        }

        # Valid
        assert field_service.validate_field(field_def, 50) is True

        # Below min
        with pytest.raises(ValueError, match="min"):
            field_service.validate_field(field_def, -1)

        # Above max
        with pytest.raises(ValueError, match="max"):
            field_service.validate_field(field_def, 101)

    def test_validate_email_field(self, field_service: FieldService):
        """Test email field validation."""
        field_def = {
            "name": "email",
            "type": "email",
        }

        # Valid
        assert field_service.validate_field(field_def, "user@example.com") is True

        # Invalid
        with pytest.raises(ValueError, match="email"):
            field_service.validate_field(field_def, "not-an-email")

    def test_validate_select_field(self, field_service: FieldService):
        """Test select field validation."""
        field_def = {
            "name": "status",
            "type": "select",
            "options": ["draft", "published", "archived"],
        }

        # Valid
        assert field_service.validate_field(field_def, "draft") is True
        assert field_service.validate_field(field_def, "published") is True

        # Invalid option
        with pytest.raises(ValueError, match="option"):
            field_service.validate_field(field_def, "invalid")

    def test_validate_url_field(self, field_service: FieldService):
        """Test URL field validation."""
        field_def = {
            "name": "website",
            "type": "url",
        }

        # Valid
        assert field_service.validate_field(field_def, "https://example.com") is True
        assert field_service.validate_field(field_def, "http://localhost:8000") is True

        # Invalid
        with pytest.raises(ValueError, match="url"):
            field_service.validate_field(field_def, "not-a-url")

    def test_validate_datetime_field(self, field_service: FieldService):
        """Test datetime field validation."""
        field_def = {
            "name": "published_at",
            "type": "datetime",
        }

        # Valid - datetime object
        assert field_service.validate_field(field_def, datetime.now()) is True

        # Valid - ISO string
        assert field_service.validate_field(field_def, "2024-01-15T10:30:00") is True

        # Invalid
        with pytest.raises(ValueError, match="datetime"):
            field_service.validate_field(field_def, "not-a-date")


class TestFieldSerialization:
    """Field serialization test cases."""

    @pytest.fixture
    def field_service(self) -> FieldService:
        return FieldService()

    def test_serialize_text(self, field_service: FieldService):
        """Test text field serialization."""
        field_def = {"name": "title", "type": "text"}

        serialized = field_service.serialize_value(field_def, "Hello World")
        assert serialized == "Hello World"

    def test_serialize_number(self, field_service: FieldService):
        """Test number field serialization."""
        field_def = {"name": "count", "type": "number"}

        serialized = field_service.serialize_value(field_def, 42)
        assert serialized == "42" or serialized == 42

    def test_serialize_boolean(self, field_service: FieldService):
        """Test boolean field serialization."""
        field_def = {"name": "is_active", "type": "boolean"}

        assert field_service.serialize_value(field_def, True) in [True, "true", "1"]
        assert field_service.serialize_value(field_def, False) in [False, "false", "0"]

    def test_serialize_json(self, field_service: FieldService):
        """Test JSON field serialization."""
        field_def = {"name": "metadata", "type": "json"}
        data = {"key": "value", "nested": {"a": 1}}

        serialized = field_service.serialize_value(field_def, data)
        assert isinstance(serialized, (str, dict))


class TestFieldDeserialization:
    """Field deserialization test cases."""

    @pytest.fixture
    def field_service(self) -> FieldService:
        return FieldService()

    def test_deserialize_text(self, field_service: FieldService):
        """Test text field deserialization."""
        field_def = {"name": "title", "type": "text"}

        value = field_service.deserialize_value(field_def, "Hello World")
        assert value == "Hello World"

    def test_deserialize_number(self, field_service: FieldService):
        """Test number field deserialization."""
        field_def = {"name": "count", "type": "number"}

        value = field_service.deserialize_value(field_def, "42")
        assert value == 42

    def test_deserialize_boolean(self, field_service: FieldService):
        """Test boolean field deserialization."""
        field_def = {"name": "is_active", "type": "boolean"}

        assert field_service.deserialize_value(field_def, "true") is True
        assert field_service.deserialize_value(field_def, "false") is False
        assert field_service.deserialize_value(field_def, "1") is True
        assert field_service.deserialize_value(field_def, "0") is False


class TestFormulaField:
    """Formula field computation tests."""

    @pytest.fixture
    def field_service(self) -> FieldService:
        return FieldService()

    def test_formula_concat(self, field_service: FieldService):
        """Test string concatenation formula."""
        field_def = {
            "name": "full_name",
            "type": "formula",
            "formula": "concat(first_name, ' ', last_name)",
        }
        context = {"first_name": "John", "last_name": "Doe"}

        result = field_service.compute_formula(field_def, context)
        assert result == "John Doe"

    def test_formula_sum(self, field_service: FieldService):
        """Test sum formula."""
        field_def = {
            "name": "total",
            "type": "formula",
            "formula": "sum(price, tax)",
        }
        context = {"price": 100, "tax": 10}

        result = field_service.compute_formula(field_def, context)
        assert result == 110

    def test_formula_conditional(self, field_service: FieldService):
        """Test conditional formula."""
        field_def = {
            "name": "label",
            "type": "formula",
            "formula": "if(status == 'active', 'Active', 'Inactive')",
        }

        result = field_service.compute_formula(field_def, {"status": "active"})
        assert result == "Active"

        result = field_service.compute_formula(field_def, {"status": "inactive"})
        assert result == "Inactive"
